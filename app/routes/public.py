from datetime import UTC, date, datetime, time
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import String, cast, false, func, literal, select, union_all

from app.auth import DbSession, public_session, new_user_session, require_csrf
from app.config import get_settings
from app.models import (
    AccountingReversal,
    AuditLog,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
    PaymentSettings,
    RecurringExpense,
    User,
    UserRole,
    UserSession,
)
from app.services.accounting import get_pool_balance
from app.services.file_storage import InvalidImageError, store_private_image
from app.services.money import (
    MAX_AMOUNT_CENTAVOS,
    format_amount,
    format_amount_input,
    parse_amount_centavos,
)
from app.web import templates

router = APIRouter()
PAGE_SIZE = 20

ANONYMOUS_USER_EMAIL = "anonymous@contribution-tracker.local"
ANONYMOUS_USER_NAME = "Anonymous Contributor"


def get_or_create_anonymous_user(db: DbSession) -> User:
    """Get or create the special anonymous user for public submissions."""
    user = db.scalar(select(User).where(User.email == ANONYMOUS_USER_EMAIL))
    if user is None:
        # Anonymous user doesn't need a real password hash since they can't log in
        from app.security import hash_password
        import secrets

        dummy_password = secrets.token_urlsafe(32)
        user = User(
            full_name=ANONYMOUS_USER_NAME,
            email=ANONYMOUS_USER_EMAIL,
            password_hash=hash_password(dummy_password),
            role=UserRole.USER,
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user


def parse_filter_date(value: str | None, *, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Filter dates must use YYYY-MM-DD format.")
    timezone = ZoneInfo(get_settings().timezone)
    boundary = time.max if end else time.min
    return datetime.combine(parsed, boundary, tzinfo=timezone).astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(ZoneInfo(get_settings().timezone)).strftime("%Y-%m-%d %H:%M")


def contribution_event_time():
    return func.coalesce(Contribution.posted_at, Contribution.created_at)


def public_transaction_query(request: Request):
    """Transaction query for public landing page - only approved contributions and posted expenses."""
    transaction_type = request.query_params.get("type", "").strip().lower()
    status_filter = request.query_params.get("status", "").strip().upper()
    account_filter = request.query_params.get("account", "").strip()
    search_filter = request.query_params.get("q", "").strip()
    from_date = parse_filter_date(request.query_params.get("from_date"))
    to_date = parse_filter_date(request.query_params.get("to_date"), end=True)
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=400, detail="The start date must not be after the end date.")

    contributions = (
        select(
            literal("contribution").label("type"),
            Contribution.id.label("id"),
            contribution_event_time().label("event_at"),
            User.full_name.label("account"),
            Contribution.payment_reference.label("description"),
            Contribution.amount_centavos.label("amount_centavos"),
            cast(Contribution.status, String).label("status"),
            literal(None).label("reason"),
        )
        .join(User, User.id == Contribution.user_id)
        .where(Contribution.status == ContributionStatus.APPROVED)
    )
    expenses = (
        select(
            literal("expense").label("type"),
            Expense.id.label("id"),
            Expense.created_at.label("event_at"),
            func.coalesce(
                RecurringExpense.name,
                User.full_name,
                literal("Scheduled expense"),
            ).label("account"),
            Expense.description.label("description"),
            (-Expense.amount_centavos).label("amount_centavos"),
            cast(Expense.status, String).label("status"),
            literal(None).label("reason"),
        )
        .outerjoin(User, User.id == Expense.created_by)
        .outerjoin(RecurringExpense, RecurringExpense.id == Expense.recurring_expense_id)
        .where(Expense.status == ExpenseStatus.POSTED)
    )
    if transaction_type in {"contribution", "expense"}:
        if transaction_type == "contribution":
            expenses = expenses.where(false())
        else:
            contributions = contributions.where(false())
    if status_filter:
        contributions = contributions.where(cast(Contribution.status, String) == status_filter)
        expenses = expenses.where(cast(Expense.status, String) == status_filter)
    if account_filter:
        contributions = contributions.where(User.full_name.ilike(f"%{account_filter}%"))
        expenses = expenses.where(
            func.coalesce(RecurringExpense.name, User.full_name, literal("Scheduled expense")).ilike(f"%{account_filter}%")
        )
    if search_filter:
        contributions = contributions.where(
            (User.full_name.ilike(f"%{search_filter}%")) | Contribution.payment_reference.ilike(f"%{search_filter}%")
        )
        expenses = expenses.where(
            (
                func.coalesce(
                    RecurringExpense.name,
                    User.full_name,
                    literal("Scheduled expense"),
                ).ilike(f"%{search_filter}%")
            )
            | Expense.description.ilike(f"%{search_filter}%")
            | Expense.category.ilike(f"%{search_filter}%")
        )
    if from_date:
        contributions = contributions.where(contribution_event_time() >= from_date)
        expenses = expenses.where(Expense.created_at >= from_date)
    if to_date:
        contributions = contributions.where(contribution_event_time() <= to_date)
        expenses = expenses.where(Expense.created_at <= to_date)
    return union_all(contributions, expenses).subquery()


@router.get("/", response_class=HTMLResponse, name="landing")
def landing_page(
    request: Request,
    db: DbSession,
    user_session: Annotated[UserSession, Depends(public_session)],
) -> HTMLResponse:
    page_number = max(1, int(request.query_params.get("page", "1")) if request.query_params.get("page", "1").isdigit() else 1)
    transactions = public_transaction_query(request)
    total_transactions = db.scalar(select(func.count()).select_from(transactions)) or 0
    page_count = max(1, (total_transactions + PAGE_SIZE - 1) // PAGE_SIZE)
    page_number = min(page_number, page_count)
    transaction_rows = db.execute(
        select(transactions)
        .order_by(transactions.c.event_at.desc(), transactions.c.id.desc())
        .offset((page_number - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    balance = get_pool_balance(db)
    approved_total = db.scalar(
        select(func.coalesce(func.sum(Contribution.amount_centavos), 0)).where(
            Contribution.status == ContributionStatus.APPROVED
        )
    )
    posted_total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_centavos), 0)).where(
            Expense.status == ExpenseStatus.POSTED
        )
    )
    contributor_count = db.scalar(
        select(func.count(func.distinct(Contribution.user_id))).where(
            Contribution.status == ContributionStatus.APPROVED
        )
    )
    payment_settings = db.get(PaymentSettings, 1)
    filters = {
        key: request.query_params.get(key, "")
        for key in ("q", "account", "type", "status", "from_date", "to_date")
    }
    submitted = request.query_params.get("submitted") == "1"
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={
            "csrf_token": user_session.data["csrf_token"],
            "format_amount": format_amount,
            "format_timestamp": format_timestamp,
            "balance": balance,
            "approved_total": int(approved_total or 0),
            "posted_total": int(posted_total or 0),
            "contributor_count": int(contributor_count or 0),
            "transactions": transaction_rows,
            "payment_settings": payment_settings,
            "filters": filters,
            "page": page_number,
            "page_count": page_count,
            "total_transactions": total_transactions,
            "submitted": submitted,
            "error": None,
            "max_upload_size": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "max_amount_php": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "is_public_page": True,
        },
    )


@router.post("/", response_class=HTMLResponse, response_model=None)
async def submit_public_contribution(
    request: Request,
    db: DbSession,
    user_session: Annotated[UserSession, Depends(public_session)],
    _csrf: Annotated[None, Depends(require_csrf)],
    amount: Annotated[str, Form(max_length=32)],
    payment_reference: Annotated[str, Form(max_length=200)],
    payment_date: Annotated[date, Form()],
    proof: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse | RedirectResponse:
    normalized_reference = payment_reference.strip()
    amount_centavos = parse_amount_centavos(amount)
    if amount_centavos is None:
        # Re-render landing page with error
        return await landing_page_with_error(request, db, user_session, "Enter a positive PHP amount with no more than two decimal places.")
    if payment_date > datetime.now(ZoneInfo(get_settings().timezone)).date():
        return await landing_page_with_error(request, db, user_session, "Payment date cannot be in the future.")
    if not normalized_reference:
        return await landing_page_with_error(request, db, user_session, "Payment reference is required.")
    if len(normalized_reference) > 200:
        return await landing_page_with_error(request, db, user_session, "Payment reference must be 200 characters or fewer.")

    proof_key: str | None = None
    proof_path = None
    if proof is not None and proof.filename:
        contents = await proof.read(get_settings().max_upload_size_bytes + 1)
        if len(contents) > get_settings().max_upload_size_bytes:
            return await landing_page_with_error(
                request,
                db,
                user_session,
                f"Proof image exceeds the {format_amount_input(get_settings().max_upload_size_bytes)} upload limit.",
            )
        try:
            proof_key, _, proof_path = store_private_image(contents)
        except InvalidImageError as error:
            return await landing_page_with_error(request, db, user_session, str(error))

    anonymous_user = get_or_create_anonymous_user(db)
    committed = False
    try:
        contribution = Contribution(
            user_id=anonymous_user.id,
            amount_centavos=amount_centavos,
            payment_reference=normalized_reference,
            payment_date=payment_date,
            proof_file_key=proof_key,
            status=ContributionStatus.PENDING,
        )
        db.add(contribution)
        db.flush()
        db.add(
            AuditLog(
                actor_user_id=anonymous_user.id,
                action="contribution.submitted",
                entity_type="contribution",
                entity_id=str(contribution.id),
                details={
                    "amount_centavos": amount_centavos,
                    "payment_reference": normalized_reference,
                    "proof_attached": proof_key is not None,
                    "anonymous": True,
                },
            )
        )
        db.commit()
        committed = True
    finally:
        if not committed and proof_path is not None:
            proof_path.unlink(missing_ok=True)
    return RedirectResponse("/?submitted=1", status_code=303)


async def landing_page_with_error(
    request: Request,
    db: DbSession,
    user_session: UserSession,
    error: str,
) -> HTMLResponse:
    """Re-render landing page with an error message."""
    page_number = max(1, int(request.query_params.get("page", "1")) if request.query_params.get("page", "1").isdigit() else 1)
    transactions = public_transaction_query(request)
    total_transactions = db.scalar(select(func.count()).select_from(transactions)) or 0
    page_count = max(1, (total_transactions + PAGE_SIZE - 1) // PAGE_SIZE)
    page_number = min(page_number, page_count)
    transaction_rows = db.execute(
        select(transactions)
        .order_by(transactions.c.event_at.desc(), transactions.c.id.desc())
        .offset((page_number - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    balance = get_pool_balance(db)
    approved_total = db.scalar(
        select(func.coalesce(func.sum(Contribution.amount_centavos), 0)).where(
            Contribution.status == ContributionStatus.APPROVED
        )
    )
    posted_total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_centavos), 0)).where(
            Expense.status == ExpenseStatus.POSTED
        )
    )
    contributor_count = db.scalar(
        select(func.count(func.distinct(Contribution.user_id))).where(
            Contribution.status == ContributionStatus.APPROVED
        )
    )
    payment_settings = db.get(PaymentSettings, 1)
    filters = {
        key: request.query_params.get(key, "")
        for key in ("q", "account", "type", "status", "from_date", "to_date")
    }
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={
            "csrf_token": user_session.data["csrf_token"],
            "format_amount": format_amount,
            "format_timestamp": format_timestamp,
            "balance": balance,
            "approved_total": int(approved_total or 0),
            "posted_total": int(posted_total or 0),
            "contributor_count": int(contributor_count or 0),
            "transactions": transaction_rows,
            "payment_settings": payment_settings,
            "filters": filters,
            "page": page_number,
            "page_count": page_count,
            "total_transactions": total_transactions,
            "submitted": False,
            "error": error,
            "max_upload_size": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "max_amount_php": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "is_public_page": True,
        },
        status_code=400,
    )