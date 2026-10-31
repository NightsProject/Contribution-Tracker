import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import utc_now


class AccountingLock(Base):
    __tablename__ = "accounting_locks"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_id"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)


class AccountingReversal(Base):
    __tablename__ = "accounting_reversals"
    __table_args__ = (
        CheckConstraint(
            "(contribution_id IS NOT NULL AND expense_id IS NULL) OR "
            "(contribution_id IS NULL AND expense_id IS NOT NULL)",
            name="exactly_one_source",
        ),
        CheckConstraint("amount_centavos > 0", name="amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contribution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contributions.id"), unique=True
    )
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expenses.id"), unique=True
    )
    amount_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
