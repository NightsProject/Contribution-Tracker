import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import TimestampMixin


class RecurringExpenseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class OccurrenceStatus(str, enum.Enum):
    POSTED = "POSTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class RecurringExpense(TimestampMixin, Base):
    __tablename__ = "recurring_expenses"
    __table_args__ = (
        CheckConstraint("amount_centavos > 0", name="amount_positive"),
        CheckConstraint("interval_days >= 1", name="interval_days_positive"),
        Index("ix_recurring_expenses_status_next_due_at", "status", "next_due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    amount_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RecurringExpenseStatus] = mapped_column(
        Enum(
            RecurringExpenseStatus,
            name="recurring_expense_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda status: [item.value for item in status],
        ),
        nullable=False,
        default=RecurringExpenseStatus.ACTIVE,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class RecurringOccurrence(Base):
    __tablename__ = "recurring_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "recurring_expense_id", "scheduled_for", name="uq_occurrence_schedule_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recurring_expense_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recurring_expenses.id"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[OccurrenceStatus] = mapped_column(
        Enum(
            OccurrenceStatus,
            name="occurrence_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda status: [item.value for item in status],
        ),
        nullable=False,
    )
    expense_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expenses.id"), unique=True
    )
    blocked_reason: Mapped[str | None] = mapped_column(String(1000))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
