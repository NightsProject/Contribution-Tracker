import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import TimestampMixin


class ExpenseStatus(str, enum.Enum):
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_centavos > 0", name="amount_positive"),
        Index("ix_expenses_expense_date", "expense_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    recurring_expense_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recurring_expenses.id")
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_file_key: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ExpenseStatus] = mapped_column(
        Enum(
            ExpenseStatus,
            name="expense_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda status: [item.value for item in status],
        ),
        nullable=False,
        default=ExpenseStatus.POSTED,
    )
