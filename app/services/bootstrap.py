from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.services.accounting import acquire_accounting_lock
from app.services.accounts import EmailAlreadyInUseError, create_account


class AdminAlreadyExistsError(Exception):
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
    return create_account(
        db,
        full_name=full_name,
        email=email,
        password=password,
        role=UserRole.ADMIN,
        action="user.bootstrap_admin_created",
    )
