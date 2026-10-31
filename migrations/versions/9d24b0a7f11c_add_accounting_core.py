"""add accounting core

Revision ID: 9d24b0a7f11c
Revises: 402c88236bc3
Create Date: 2026-10-31 15:39:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d24b0a7f11c"
down_revision: Union[str, None] = "402c88236bc3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounting_locks",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_accounting_locks_singleton_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_locks")),
    )
    op.execute("INSERT INTO accounting_locks (id) VALUES (1)")
    op.create_table(
        "accounting_reversals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contribution_id", sa.Uuid(), nullable=True),
        sa.Column("expense_id", sa.Uuid(), nullable=True),
        sa.Column("amount_centavos", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(contribution_id IS NOT NULL AND expense_id IS NULL) OR "
            "(contribution_id IS NULL AND expense_id IS NOT NULL)",
            name=op.f("ck_accounting_reversals_exactly_one_source"),
        ),
        sa.CheckConstraint(
            "amount_centavos > 0",
            name=op.f("ck_accounting_reversals_amount_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_accounting_reversals_actor_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["contribution_id"],
            ["contributions.id"],
            name=op.f("fk_accounting_reversals_contribution_id_contributions"),
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"],
            ["expenses.id"],
            name=op.f("fk_accounting_reversals_expense_id_expenses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_reversals")),
        sa.UniqueConstraint(
            "contribution_id",
            name=op.f("uq_accounting_reversals_contribution_id"),
        ),
        sa.UniqueConstraint(
            "expense_id",
            name=op.f("uq_accounting_reversals_expense_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("accounting_reversals")
    op.drop_table("accounting_locks")
