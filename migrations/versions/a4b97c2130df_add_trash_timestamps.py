"""add reversible trash timestamps

Revision ID: a4b97c2130df
Revises: 9d24b0a7f11c
Create Date: 2026-10-31 17:36:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4b97c2130df"
down_revision: Union[str, None] = "9d24b0a7f11c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "contributions",
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("expenses", sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("expenses", "trashed_at")
    op.drop_column("contributions", "trashed_at")
    op.drop_column("users", "trashed_at")
