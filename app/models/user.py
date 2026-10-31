import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.common import TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda role: [item.value for item in role],
        ),
        nullable=False,
        default=UserRole.USER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
