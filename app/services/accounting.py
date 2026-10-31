from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import (
    AccountingLock,
    AccountingReversal,
    AuditLog,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
)
from app.models.common import utc_now
from app.services.money import MAX_AMOUNT_CENTAVOS

ACCOUNTING_LOCK_ID = 1


class AccountingError(Exception):
    pass


class InvalidFinancialRecordError(AccountingError):
    pass


class InsufficientFundsError(AccountingError):
    pass


class FinancialStateError(AccountingError):
    pass


@dataclass(frozen=True)
class PoolBalance:
    approved_contributions_centavos: int
    posted_expenses_centavos: int

    @property
    def available_centavos(self) -> int:
        return self.approved_contributions_centavos - self.posted_expenses_centavos


def acquire_accounting_lock(db: Session) -> None:
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(
            postgresql_insert(AccountingLock)
            .values(id=ACCOUNTING_LOCK_ID)
            .on_conflict_do_nothing(index_elements=[AccountingLock.id])
        )
    elif dialect == "sqlite":
        db.execute(
            sqlite_insert(AccountingLock)
            .values(id=ACCOUNTING_LOCK_ID)
            .on_conflict_do_nothing(index_elements=[AccountingLock.id])
        )
    else:
        if db.get(AccountingLock, ACCOUNTING_LOCK_ID) is None:
            db.add(AccountingLock(id=ACCOUNTING_LOCK_ID))
            db.flush()

    db.scalar(
        select(AccountingLock)
        .where(AccountingLock.id == ACCOUNTING_LOCK_ID)
        .with_for_update()
    )


def get_pool_balance(db: Session) -> PoolBalance:
    approved_contributions = db.scalar(
        select(func.coalesce(func.sum(Contribution.amount_centavos), 0)).where(
            Contribution.status == ContributionStatus.APPROVED
        )
    )
    posted_expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_centavos), 0)).where(
            Expense.status == ExpenseStatus.POSTED
        )
    )
    return PoolBalance(
        approved_contributions_centavos=int(approved_contributions or 0),
        posted_expenses_centavos=int(posted_expenses or 0),
    )


def post_expense(
    db: Session,
    *,
    actor_user_id: UUID,
    description: str,
    category: str,
    amount_centavos: int,
    expense_date: date,
    receipt_file_key: str | None = None,
) -> Expense:
    normalized_description = description.strip()
    normalized_category = category.strip()
    if (
        not normalized_description
        or len(normalized_description) > 500
        or not normalized_category
        or len(normalized_category) > 100
        or not 0 < amount_centavos <= MAX_AMOUNT_CENTAVOS
    ):
        raise InvalidFinancialRecordError("Enter a description, category, and valid positive amount.")

    acquire_accounting_lock(db)
    balance = get_pool_balance(db)
    if amount_centavos > balance.available_centavos:
        db.rollback()
        raise InsufficientFundsError("Expense exceeds the available pool balance.")

    expense = Expense(
        description=normalized_description,
        category=normalized_category,
        amount_centavos=amount_centavos,
        expense_date=expense_date,
        created_by=actor_user_id,
        receipt_file_key=receipt_file_key,
        status=ExpenseStatus.POSTED,
    )
    db.add(expense)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="expense.posted",
            entity_type="expense",
            entity_id=str(expense.id),
            details={
                "amount_centavos": amount_centavos,
                "category": normalized_category,
                "description": normalized_description,
                "receipt_attached": receipt_file_key is not None,
            },
        )
    )
    db.commit()
    return expense


def reverse_contribution(
    db: Session,
    *,
    contribution_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> AccountingReversal:
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 1000:
        raise InvalidFinancialRecordError("A reversal reason of 1 to 1000 characters is required.")

    acquire_accounting_lock(db)
    contribution = db.scalar(
        select(Contribution)
        .where(Contribution.id == contribution_id)
        .with_for_update()
    )
    if contribution is None or contribution.status != ContributionStatus.APPROVED:
        db.rollback()
        raise FinancialStateError("Only an approved contribution can be reversed.")
    if contribution.amount_centavos > get_pool_balance(db).available_centavos:
        db.rollback()
        raise InsufficientFundsError(
            "The contribution cannot be reversed because those funds have already been spent."
        )

    contribution.status = ContributionStatus.REVERSED
    contribution.updated_at = utc_now()
    reversal = AccountingReversal(
        contribution_id=contribution.id,
        amount_centavos=contribution.amount_centavos,
        reason=normalized_reason,
        actor_user_id=actor_user_id,
    )
    db.add(reversal)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="contribution.reversed",
            entity_type="contribution",
            entity_id=str(contribution.id),
            details={
                "amount_centavos": contribution.amount_centavos,
                "reason": normalized_reason,
                "reversal_id": str(reversal.id),
            },
        )
    )
    db.commit()
    return reversal


def reverse_expense(
    db: Session,
    *,
    expense_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> AccountingReversal:
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 1000:
        raise InvalidFinancialRecordError("A reversal reason of 1 to 1000 characters is required.")

    acquire_accounting_lock(db)
    expense = db.scalar(select(Expense).where(Expense.id == expense_id).with_for_update())
    if expense is None or expense.status != ExpenseStatus.POSTED:
        db.rollback()
        raise FinancialStateError("Only a posted expense can be reversed.")

    expense.status = ExpenseStatus.REVERSED
    expense.updated_at = utc_now()
    reversal = AccountingReversal(
        expense_id=expense.id,
        amount_centavos=expense.amount_centavos,
        reason=normalized_reason,
        actor_user_id=actor_user_id,
    )
    db.add(reversal)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="expense.reversed",
            entity_type="expense",
            entity_id=str(expense.id),
            details={
                "amount_centavos": expense.amount_centavos,
                "reason": normalized_reason,
                "reversal_id": str(reversal.id),
            },
        )
    )
    db.commit()
    return reversal
