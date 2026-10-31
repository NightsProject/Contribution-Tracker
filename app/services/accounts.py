from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, User, UserRole
from app.security import hash_password


class EmailAlreadyInUseError(Exception):
    pass


def is_duplicate_email_error(error: IntegrityError) -> bool:
    constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint_name == "uq_users_email":
        return True
    return "UNIQUE constraint failed: users.email" in str(error.orig)


def create_account(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
    role: UserRole,
    action: str,
    actor_user_id: UUID | None = None,
) -> User:
    if db.scalar(select(User.id).where(User.email == email).limit(1)) is not None:
        raise EmailAlreadyInUseError

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if not is_duplicate_email_error(error):
            raise
        raise EmailAlreadyInUseError from error

    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            details={"email": email, "role": role.value},
        )
    )
    return user
