from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User, UserRole
from app.security import hash_password
from app.services.accounting import acquire_accounting_lock


class AdminAlreadyExistsError(Exception):
    pass


class EmailAlreadyInUseError(Exception):
    pass


def has_admin_account(db: Session) -> bool:
    return (
        db.scalar(select(User.id).where(User.role == UserRole.ADMIN).limit(1))
        is not None
    )


def create_initial_admin(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
) -> User:
    acquire_accounting_lock(db)
    if has_admin_account(db):
        raise AdminAlreadyExistsError
    if db.scalar(select(User.id).where(User.email == email).limit(1)) is not None:
        raise EmailAlreadyInUseError

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            action="user.bootstrap_admin_created",
            entity_type="user",
            entity_id=str(user.id),
            details={"email": email, "role": UserRole.ADMIN.value},
        )
    )
    return user
