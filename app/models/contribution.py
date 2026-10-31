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


class ContributionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VOIDED = "VOIDED"
    REVERSED = "REVERSED"


class Contribution(TimestampMixin, Base):
    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint("amount_centavos > 0", name="amount_positive"),
        Index("ix_contributions_user_created_at", "user_id", "created_at"),
        Index("ix_contributions_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    amount_centavos: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    proof_file_key: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ContributionStatus] = mapped_column(
        Enum(
            ContributionStatus,
            name="contribution_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda status: [item.value for item in status],
        ),
        nullable=False,
        default=ContributionStatus.PENDING,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(1000))
    void_reason: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
