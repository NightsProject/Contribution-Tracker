from app.database import Base
from sqlalchemy import UniqueConstraint

import app.models  # noqa: F401


def test_initial_schema_contains_design_entities() -> None:
    assert set(Base.metadata.tables) == {
        "accounting_locks",
        "accounting_reversals",
        "audit_logs",
        "contributions",
        "expenses",
        "login_attempts",
        "payment_settings",
        "recurring_expenses",
        "recurring_occurrences",
        "sessions",
        "users",
    }


def test_recurring_occurrences_are_unique_per_schedule_and_due_time() -> None:
    table = Base.metadata.tables["recurring_occurrences"]
    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("recurring_expense_id", "scheduled_for") in unique_constraints


def test_pre_authentication_sessions_allow_null_user() -> None:
    user_id = Base.metadata.tables["sessions"].columns["user_id"]

    assert user_id.nullable
