"""replace transaction trash with financial corrections

Revision ID: c185a38d4192
Revises: a4b97c2130df
Create Date: 2026-10-31 17:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c185a38d4192"
down_revision: Union[str, None] = "a4b97c2130df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("contributions") as batch_op:
        batch_op.drop_constraint(op.f("ck_contributions_contribution_status"), type_="check")
        batch_op.add_column(sa.Column("void_reason", sa.String(length=1000), nullable=True))
        batch_op.drop_column("trashed_at")
        batch_op.create_check_constraint(
            "contribution_status",
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'VOIDED', 'REVERSED')",
        )
    with op.batch_alter_table("expenses") as batch_op:
        batch_op.drop_column("trashed_at")


def downgrade() -> None:
    op.execute(
        "UPDATE contributions SET status = 'REJECTED', "
        "rejection_reason = COALESCE(rejection_reason, void_reason) "
        "WHERE status = 'VOIDED'"
    )
    with op.batch_alter_table("contributions") as batch_op:
        batch_op.drop_constraint(op.f("ck_contributions_contribution_status"), type_="check")
        batch_op.add_column(sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.drop_column("void_reason")
        batch_op.create_check_constraint(
            "contribution_status",
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'REVERSED')",
        )
    with op.batch_alter_table("expenses") as batch_op:
        batch_op.add_column(sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
