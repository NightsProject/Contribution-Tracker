from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    AccountingReversal,
    AuditLog,
    Contribution,
    ContributionStatus,
    Expense,
    ExpenseStatus,
    User,
    UserRole,
)
from app.security import hash_password
from app.services.accounting import (
    FinancialStateError,
    InsufficientFundsError,
    get_pool_balance,
    post_expense,
    reverse_contribution,
    reverse_expense,
)

PASSWORD = "correct horse battery staple"


def create_user(test_db) -> uuid.UUID:
    with test_db() as db:
        user = User(
            full_name="Accounting Admin",
            email="accounting-admin@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user.id


def add_contribution(db, user_id: uuid.UUID, amount: int, status: ContributionStatus) -> UUID:
    contribution = Contribution(
        user_id=user_id,
        amount_centavos=amount,
        payment_reference=f"TXN-{uuid4()}",
        payment_date=date.today(),
        status=status,
    )
    db.add(contribution)
    db.flush()
    return contribution.id


def test_balance_counts_only_approved_contributions_and_posted_expenses(test_db) -> None:
    user_id = create_user(test_db)
    with test_db() as db:
        add_contribution(db, user_id, 10_000, ContributionStatus.APPROVED)
        add_contribution(db, user_id, 5_000, ContributionStatus.PENDING)
        add_contribution(db, user_id, 2_500, ContributionStatus.REJECTED)
        db.add_all(
            [
                Expense(
                    description="Posted",
                    category="Operations",
                    amount_centavos=3_000,
                    expense_date=date.today(),
                    status=ExpenseStatus.POSTED,
                ),
                Expense(
                    description="Reversed",
                    category="Operations",
                    amount_centavos=900,
                    expense_date=date.today(),
                    status=ExpenseStatus.REVERSED,
                ),
            ]
        )
        db.commit()

        balance = get_pool_balance(db)

    assert balance.approved_contributions_centavos == 10_000
    assert balance.posted_expenses_centavos == 3_000
    assert balance.available_centavos == 7_000


def test_post_expense_is_atomic_audited_and_checks_available_balance(test_db) -> None:
    user_id = create_user(test_db)
    with test_db() as db:
        add_contribution(db, user_id, 10_000, ContributionStatus.APPROVED)
        db.commit()

        posted = post_expense(
            db,
            actor_user_id=user_id,
            description="Office supplies",
            category="Supplies",
            amount_centavos=4_000,
            expense_date=date.today(),
        )
        assert get_pool_balance(db).available_centavos == 6_000
        assert db.scalar(
            select(AuditLog.action).where(AuditLog.entity_id == str(posted.id))
        ) == "expense.posted"

        with pytest.raises(InsufficientFundsError):
            post_expense(
                db,
                actor_user_id=user_id,
                description="Too expensive",
                category="Supplies",
                amount_centavos=6_001,
                expense_date=date.today(),
            )

        assert db.scalar(select(Expense).where(Expense.description == "Too expensive")) is None
        assert get_pool_balance(db).available_centavos == 6_000


def test_financial_reversals_record_actor_reason_and_preserve_balance_integrity(test_db) -> None:
    user_id = create_user(test_db)
    with test_db() as db:
        contribution_id = add_contribution(db, user_id, 10_000, ContributionStatus.APPROVED)
        db.commit()
        expense = post_expense(
            db,
            actor_user_id=user_id,
            description="Equipment",
            category="Equipment",
            amount_centavos=3_000,
            expense_date=date.today(),
        )

        with pytest.raises(InsufficientFundsError):
            reverse_contribution(
                db,
                contribution_id=contribution_id,
                actor_user_id=user_id,
                reason="Payment was refunded.",
            )
        assert get_pool_balance(db).available_centavos == 7_000

        expense_reversal = reverse_expense(
            db,
            expense_id=expense.id,
            actor_user_id=user_id,
            reason="Duplicate expense entry.",
        )
        assert expense_reversal.expense_id == expense.id
        assert get_pool_balance(db).available_centavos == 10_000

        contribution_reversal = reverse_contribution(
            db,
            contribution_id=contribution_id,
            actor_user_id=user_id,
            reason="Payment was refunded.",
        )
        assert contribution_reversal.contribution_id == contribution_id
        assert get_pool_balance(db).available_centavos == 0

        reversals = db.scalars(select(AccountingReversal)).all()
        assert {
            (item.expense_id, item.contribution_id, item.reason)
            for item in reversals
        } == {
            (expense.id, None, "Duplicate expense entry."),
            (None, contribution_id, "Payment was refunded."),
        }
        assert all(item.actor_user_id == user_id for item in reversals)

        with pytest.raises(FinancialStateError):
            reverse_expense(
                db,
                expense_id=expense.id,
                actor_user_id=user_id,
                reason="Attempt duplicate reversal.",
            )


def test_concurrent_expenses_cannot_spend_the_same_balance(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'accounting.db'}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    user_id = uuid4()
    with test_session() as db:
        db.add(
            User(
                id=user_id,
                full_name="Concurrent Admin",
                email="concurrent-admin@example.com",
                password_hash=hash_password(PASSWORD),
                role=UserRole.ADMIN,
                is_active=True,
            )
        )
        add_contribution(db, user_id, 10_000, ContributionStatus.APPROVED)
        db.commit()

    start = Barrier(2)

    def attempt_expense() -> str:
        with test_session() as db:
            start.wait()
            try:
                post_expense(
                    db,
                    actor_user_id=user_id,
                    description="Concurrent purchase",
                    category="Operations",
                    amount_centavos=8_000,
                    expense_date=date.today(),
                )
            except InsufficientFundsError:
                return "rejected"
            return "posted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt_expense(), range(2)))

    assert sorted(results) == ["posted", "rejected"]
    with test_session() as db:
        assert get_pool_balance(db).available_centavos == 2_000
        assert db.scalar(select(Expense.id)) is not None
    engine.dispose()
