from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DbSession, admin_user, current_session, require_csrf
from app.config import get_settings
from app.models import (
    AuditLog,
    OccurrenceStatus,
    RecurringExpense,
    RecurringExpenseStatus,
    RecurringOccurrence,
    User,
    UserSession,
)
from app.services.money import (
    MAX_AMOUNT_CENTAVOS,
    format_amount,
    format_amount_input,
    format_amount_input,
    parse_amount_centavos,
)
from app.services.recurring_expenses import (
    RecurringExpenseStateError,
    as_utc,
    process_next_occurrence,
)
from app.web import templates

router = APIRouter(prefix="/admin/recurring-expenses")
AdminDependency = Annotated[User, Depends(admin_user)]
CsrfDependency = Annotated[None, Depends(require_csrf)]


def parse_local_datetime(value: str, *, optional: bool = False) -> datetime | None:
    normalized = value.strip()
    if not normalized and optional:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return None
    return parsed.replace(tzinfo=ZoneInfo(get_settings().timezone)).astimezone(UTC)


def local_datetime_input(value: datetime) -> str:
    return as_utc(value).astimezone(ZoneInfo(get_settings().timezone)).strftime("%Y-%m-%dT%H:%M")


def recurring_page(
    request: Request,
    db: Session,
    administrator: User,
    csrf_token: str,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    schedules = db.scalars(
        select(RecurringExpense).order_by(
            RecurringExpense.status,
            RecurringExpense.next_due_at,
            RecurringExpense.name,
        )
    ).all()
    blocked = db.execute(
        select(RecurringOccurrence, RecurringExpense)
        .join(RecurringExpense, RecurringExpense.id == RecurringOccurrence.recurring_expense_id)
        .where(RecurringOccurrence.status == OccurrenceStatus.BLOCKED)
        .order_by(RecurringOccurrence.scheduled_for, RecurringOccurrence.id)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="recurring_expenses.html",
        context={
            "administrator": administrator,
            "csrf_token": csrf_token,
            "schedules": schedules,
            "blocked": blocked,
            "error": error or request.query_params.get("error"),
            "saved": request.query_params.get("saved") == "1",
            "format_amount": format_amount,
            "format_amount_input": format_amount_input,
            "local_datetime_input": local_datetime_input,
            "max_amount_php": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "settings_timezone": get_settings().timezone,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def manage_recurring_expenses(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    return recurring_page(request, db, administrator, user_session.data["csrf_token"])


@router.post("", response_class=HTMLResponse, response_model=None)
def create_recurring_expense(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: CsrfDependency,
    name: Annotated[str, Form(max_length=200)],
    description: Annotated[str, Form(max_length=1000)] = "",
    category: Annotated[str, Form(max_length=100)] = "",
    amount: Annotated[str, Form(max_length=32)] = "",
    interval_days: Annotated[int, Form()] = 1,
    start_date: Annotated[str, Form()] = "",
    end_date: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    normalized_name = name.strip()
    normalized_category = category.strip()
    amount_centavos = parse_amount_centavos(amount)
    starts_at = parse_local_datetime(start_date)
    ends_at = parse_local_datetime(end_date, optional=True)
    if (
        not normalized_name
        or not normalized_category
        or amount_centavos is None
        or interval_days < 1
        or starts_at is None
        or (end_date.strip() and ends_at is None)
        or (ends_at is not None and ends_at < starts_at)
    ):
        return recurring_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            "Enter a name, category, valid positive amount, interval of at least one day, and valid schedule dates.",
            400,
        )

    schedule = RecurringExpense(
        name=normalized_name,
        description=description.strip() or None,
        amount_centavos=amount_centavos,
        category=normalized_category,
        interval_days=interval_days,
        start_date=starts_at,
        end_date=ends_at,
        next_due_at=starts_at,
        status=RecurringExpenseStatus.ACTIVE,
        created_by=administrator.id,
        updated_by=administrator.id,
    )
    db.add(schedule)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=administrator.id,
            action="recurring_schedule.created",
            entity_type="recurring_expense",
            entity_id=str(schedule.id),
            details={
                "amount_centavos": amount_centavos,
                "category": normalized_category,
                "interval_days": interval_days,
                "start_date": starts_at.isoformat(),
            },
        )
    )
    db.commit()
    return RedirectResponse("/admin/recurring-expenses?saved=1", status_code=303)


@router.post("/{schedule_id}/edit", response_class=HTMLResponse, response_model=None)
def edit_recurring_expense(
    request: Request,
    schedule_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: CsrfDependency,
    name: Annotated[str, Form(max_length=200)],
    description: Annotated[str, Form(max_length=1000)] = "",
    category: Annotated[str, Form(max_length=100)] = "",
    amount: Annotated[str, Form(max_length=32)] = "",
    interval_days: Annotated[int, Form()] = 1,
    end_date: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    schedule = db.scalar(
        select(RecurringExpense)
        .where(RecurringExpense.id == schedule_id)
        .with_for_update()
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Recurring expense schedule not found.")
    normalized_name = name.strip()
    normalized_category = category.strip()
    amount_centavos = parse_amount_centavos(amount)
    ends_at = parse_local_datetime(end_date, optional=True)
    if (
        not normalized_name
        or not normalized_category
        or amount_centavos is None
        or interval_days < 1
        or (end_date.strip() and ends_at is None)
        or (ends_at is not None and ends_at < as_utc(schedule.start_date))
    ):
        return recurring_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            "Enter a name, category, valid positive amount, interval of at least one day, and valid end date.",
            400,
        )

    previous_values = {
        "amount_centavos": schedule.amount_centavos,
        "category": schedule.category,
        "interval_days": schedule.interval_days,
        "name": schedule.name,
    }
    schedule.name = normalized_name
    schedule.description = description.strip() or None
    schedule.category = normalized_category
    schedule.amount_centavos = amount_centavos
    schedule.interval_days = interval_days
    schedule.end_date = ends_at
    schedule.updated_by = administrator.id
    schedule.updated_at = datetime.now(UTC)
    db.add(
        AuditLog(
            actor_user_id=administrator.id,
            action="recurring_schedule.updated",
            entity_type="recurring_expense",
            entity_id=str(schedule.id),
            details={
                "previous": previous_values,
                "amount_centavos": amount_centavos,
                "category": normalized_category,
                "interval_days": interval_days,
                "interval_effective_after": as_utc(schedule.next_due_at).isoformat(),
                "name": normalized_name,
                "description": description.strip() or None,
            },
        )
    )
    db.commit()
    return RedirectResponse("/admin/recurring-expenses?saved=1", status_code=303)


def change_schedule_state(
    *,
    schedule_id: UUID,
    administrator: User,
    db: Session,
    target_status: RecurringExpenseStatus,
) -> None:
    schedule = db.scalar(
        select(RecurringExpense)
        .where(RecurringExpense.id == schedule_id)
        .with_for_update()
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Recurring expense schedule not found.")
    allowed = {
        RecurringExpenseStatus.PAUSED: {RecurringExpenseStatus.ACTIVE},
        RecurringExpenseStatus.ACTIVE: {RecurringExpenseStatus.PAUSED},
        RecurringExpenseStatus.ENDED: {
            RecurringExpenseStatus.ACTIVE,
            RecurringExpenseStatus.PAUSED,
        },
    }
    if schedule.status not in allowed[target_status]:
        raise HTTPException(status_code=409, detail="Recurring expense schedule cannot change to that state.")
    previous_status = schedule.status
    schedule.status = target_status
    schedule.updated_by = administrator.id
    schedule.updated_at = datetime.now(UTC)
    db.add(
        AuditLog(
            actor_user_id=administrator.id,
            action=f"recurring_schedule.{target_status.value.lower()}",
            entity_type="recurring_expense",
            entity_id=str(schedule.id),
            details={"previous_status": previous_status.value, "status": target_status.value},
        )
    )
    db.commit()


@router.post("/{schedule_id}/pause")
def pause_recurring_expense(
    schedule_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
) -> RedirectResponse:
    change_schedule_state(
        schedule_id=schedule_id,
        administrator=administrator,
        db=db,
        target_status=RecurringExpenseStatus.PAUSED,
    )
    return RedirectResponse("/admin/recurring-expenses?saved=1", status_code=303)


@router.post("/{schedule_id}/resume")
def resume_recurring_expense(
    schedule_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
) -> RedirectResponse:
    change_schedule_state(
        schedule_id=schedule_id,
        administrator=administrator,
        db=db,
        target_status=RecurringExpenseStatus.ACTIVE,
    )
    return RedirectResponse("/admin/recurring-expenses?saved=1", status_code=303)


@router.post("/{schedule_id}/end")
def end_recurring_expense(
    schedule_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
) -> RedirectResponse:
    change_schedule_state(
        schedule_id=schedule_id,
        administrator=administrator,
        db=db,
        target_status=RecurringExpenseStatus.ENDED,
    )
    return RedirectResponse("/admin/recurring-expenses?saved=1", status_code=303)


@router.post("/occurrences/{occurrence_id}/retry")
def retry_blocked_occurrence(
    occurrence_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
) -> RedirectResponse:
    occurrence = db.get(RecurringOccurrence, occurrence_id)
    if occurrence is None or occurrence.status != OccurrenceStatus.BLOCKED:
        raise HTTPException(status_code=409, detail="Occurrence is not blocked.")
    try:
        status = process_next_occurrence(
            db,
            schedule_id=occurrence.recurring_expense_id,
            now=datetime.now(UTC),
            retry_blocked=True,
            actor_user_id=administrator.id,
        )
    except RecurringExpenseStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if status == OccurrenceStatus.POSTED:
        return RedirectResponse("/admin/recurring-expenses?saved=1", status_code=303)
    return RedirectResponse(
        "/admin/recurring-expenses?error=The+occurrence+is+still+blocked+by+insufficient+funds.",
        status_code=303,
    )
