from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AuditLog,
    Expense,
    ExpenseStatus,
    OccurrenceStatus,
    RecurringExpense,
    RecurringExpenseStatus,
    RecurringOccurrence,
)
from app.models.common import utc_now
from app.services.accounting import acquire_accounting_lock, get_pool_balance


class RecurringExpenseStateError(Exception):
    pass


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def next_scheduled_time(scheduled_for: datetime, interval_days: int) -> datetime:
    timezone = ZoneInfo(get_settings().timezone)
    local_time = as_utc(scheduled_for).astimezone(timezone)
    return (local_time + timedelta(days=interval_days)).astimezone(UTC)


def process_next_occurrence(
    db: Session,
    *,
    schedule_id: UUID,
    now: datetime,
    retry_blocked: bool = False,
    actor_user_id: UUID | None = None,
) -> OccurrenceStatus | None:
    schedule = db.scalar(
        select(RecurringExpense)
        .where(RecurringExpense.id == schedule_id)
        .with_for_update()
    )
    if schedule is None:
        return None

    scheduled_for = as_utc(schedule.next_due_at)
    now_utc = as_utc(now)
    end_date = as_utc(schedule.end_date) if schedule.end_date is not None else None
    if schedule.status != RecurringExpenseStatus.ACTIVE and not retry_blocked:
        return None
    if end_date is not None and scheduled_for > end_date:
        if schedule.status == RecurringExpenseStatus.ACTIVE:
            schedule.status = RecurringExpenseStatus.ENDED
            schedule.updated_at = utc_now()
            db.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    action="recurring_schedule.ended",
                    entity_type="recurring_expense",
                    entity_id=str(schedule.id),
                    details={"reason": "end_date_reached"},
                )
            )
            db.commit()
        return None
    if not retry_blocked and scheduled_for > now_utc:
        return None

    occurrence = db.scalar(
        select(RecurringOccurrence)
        .where(
            RecurringOccurrence.recurring_expense_id == schedule.id,
            RecurringOccurrence.scheduled_for == scheduled_for,
        )
        .with_for_update()
    )
    if occurrence is not None:
        if occurrence.status == OccurrenceStatus.BLOCKED and retry_blocked:
            pass
        elif occurrence.status == OccurrenceStatus.POSTED:
            schedule.next_due_at = next_scheduled_time(
                scheduled_for, schedule.interval_days
            )
            schedule.last_generated_at = occurrence.posted_at
            schedule.updated_at = utc_now()
            if end_date is not None and schedule.next_due_at > end_date:
                schedule.status = RecurringExpenseStatus.ENDED
            db.commit()
            return OccurrenceStatus.POSTED
        else:
            return occurrence.status
    elif retry_blocked:
        raise RecurringExpenseStateError("There is no blocked occurrence to retry.")

    acquire_accounting_lock(db)
    balance = get_pool_balance(db)
    attempted_at = utc_now()
    if schedule.amount_centavos > balance.available_centavos:
        if occurrence is None:
            occurrence = RecurringOccurrence(
                recurring_expense_id=schedule.id,
                scheduled_for=scheduled_for,
                status=OccurrenceStatus.BLOCKED,
            )
            db.add(occurrence)
        occurrence.status = OccurrenceStatus.BLOCKED
        occurrence.blocked_reason = "Insufficient funds."
        occurrence.attempted_at = attempted_at
        db.flush()
        db.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action="recurring_occurrence.blocked",
                entity_type="recurring_occurrence",
                entity_id=str(occurrence.id),
                details={
                    "amount_centavos": schedule.amount_centavos,
                    "scheduled_for": scheduled_for.isoformat(),
                    "available_centavos": balance.available_centavos,
                },
            )
        )
        db.commit()
        return OccurrenceStatus.BLOCKED

    timezone = ZoneInfo(get_settings().timezone)
    expense = Expense(
        description=schedule.name,
        category=schedule.category,
        amount_centavos=schedule.amount_centavos,
        expense_date=scheduled_for.astimezone(timezone).date(),
        recurring_expense_id=schedule.id,
        scheduled_for=scheduled_for,
        status=ExpenseStatus.POSTED,
    )
    db.add(expense)
    db.flush()
    if occurrence is None:
        occurrence = RecurringOccurrence(
            recurring_expense_id=schedule.id,
            scheduled_for=scheduled_for,
            status=OccurrenceStatus.POSTED,
            expense_id=expense.id,
            attempted_at=attempted_at,
            posted_at=attempted_at,
        )
        db.add(occurrence)
    else:
        occurrence.status = OccurrenceStatus.POSTED
        occurrence.expense_id = expense.id
        occurrence.blocked_reason = None
        occurrence.attempted_at = attempted_at
        occurrence.posted_at = attempted_at
    schedule.last_generated_at = attempted_at
    schedule.next_due_at = next_scheduled_time(scheduled_for, schedule.interval_days)
    schedule.updated_at = attempted_at
    if end_date is not None and schedule.next_due_at > end_date:
        schedule.status = RecurringExpenseStatus.ENDED
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="recurring_occurrence.posted",
            entity_type="recurring_occurrence",
            entity_id=str(occurrence.id),
            details={
                "amount_centavos": expense.amount_centavos,
                "expense_id": str(expense.id),
                "scheduled_for": scheduled_for.isoformat(),
            },
        )
    )
    db.commit()
    return OccurrenceStatus.POSTED


def process_schedule(
    db: Session,
    *,
    schedule_id: UUID,
    now: datetime,
) -> int:
    posted = 0
    while True:
        status = process_next_occurrence(db, schedule_id=schedule_id, now=now)
        if status != OccurrenceStatus.POSTED:
            return posted
        posted += 1
