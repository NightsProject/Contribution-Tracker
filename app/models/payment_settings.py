import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import utc_now


class PaymentSettings(Base):
    __tablename__ = "payment_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton_id"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    payment_method: Mapped[str | None] = mapped_column(String(100))
    account_name: Mapped[str | None] = mapped_column(String(200))
    account_identifier: Mapped[str | None] = mapped_column(String(200))
    instructions: Mapped[str | None] = mapped_column(Text)
    qr_file_key: Mapped[str | None] = mapped_column(String(500))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
