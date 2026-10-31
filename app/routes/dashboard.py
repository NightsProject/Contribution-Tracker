from typing import Annotated
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import String, cast, func, literal, select, union_all

from app.auth import DbSession, current_session, signed_in_user
from app.config import get_settings
from app.models import (
    AccountingReversal,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
    PaymentSettings,
    RecurringExpense,
    User,
    UserSession,
)
from app.services.accounting import get_pool_balance
from app.services.money import format_amount
from app.web import templates

router = APIRouter()
PAGE_SIZE = 20


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


def transaction_query(user: User, request: Request):
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
            func.coalesce(
                Contribution.void_reason,
                select(AccountingReversal.reason)
                .where(AccountingReversal.contribution_id == Contribution.id)
                .scalar_subquery(),
            ).label("reason"),
        )
        .join(User, User.id == Contribution.user_id)
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
            select(AccountingReversal.reason)
            .where(AccountingReversal.expense_id == Expense.id)
            .scalar_subquery()
            .label("reason"),
        )
        .outerjoin(User, User.id == Expense.created_by)
        .outerjoin(RecurringExpense, RecurringExpense.id == Expense.recurring_expense_id)
    )
    if user.role.value != "ADMIN":
        contributions = contributions.where(
            (Contribution.status == ContributionStatus.APPROVED)
            | (Contribution.user_id == user.id)
        )
    if transaction_type in {"contribution", "expense"}:
        if transaction_type == "contribution":
            expenses = expenses.where(False)
        else:
            contributions = contributions.where(False)
    if status_filter:
        contributions = contributions.where(cast(Contribution.status, String) == status_filter)
        expenses = expenses.where(cast(Expense.status, String) == status_filter)
    if account_filter:
        contributions = contributions.where(User.full_name.ilike(f"%{account_filter}%"))
        expenses = expenses.where(
            func.coalesce(RecurringExpense.name, User.full_name, literal("Scheduled expense"))
            .ilike(f"%{account_filter}%")
        )
    if search_filter:
        contributions = contributions.where(
            (User.full_name.ilike(f"%{search_filter}%"))
            | Contribution.payment_reference.ilike(f"%{search_filter}%")
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


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(signed_in_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    page_number = max(1, int(request.query_params.get("page", "1")) if request.query_params.get("page", "1").isdigit() else 1)
    transactions = transaction_query(user, request)
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
        name="dashboard.html",
        context={
            "user": user,
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
            "transaction_action": request.query_params.get("transaction_action", ""),
        },
    )
