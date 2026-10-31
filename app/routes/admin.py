from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import DbSession, admin_user, current_session, require_csrf
from app.models import AuditLog, User, UserRole, UserSession
from app.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password, valid_email
from app.services.accounts import (
    EmailAlreadyInUseError,
    create_account,
    is_duplicate_email_error,
)
from app.web import templates

router = APIRouter(prefix="/admin")
AdminDependency = Annotated[User, Depends(admin_user)]
CsrfDependency = Annotated[None, Depends(require_csrf)]


def parse_role(role: str) -> UserRole | None:
    try:
        return UserRole(role)
    except ValueError:
        return None


def users_page(
    request: Request,
    db: Session,
    administrator: User,
    csrf_token: str,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    users = db.scalars(select(User).order_by(User.full_name, User.email)).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "administrator": administrator,
            "csrf_token": csrf_token,
            "users": users,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/users", response_class=HTMLResponse)
def manage_users(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    return users_page(request, db, administrator, user_session.data["csrf_token"])


@router.post("/users", response_class=HTMLResponse, response_model=None)
def create_user(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
    csrf_token: Annotated[str, Form()],
    full_name: Annotated[str, Form(max_length=200)],
    email: Annotated[str, Form(max_length=320)],
    password: Annotated[str, Form(max_length=1024)],
    role: Annotated[str, Form()] = "USER",
) -> HTMLResponse:
    name = full_name.strip()
    normalized_email = email.strip().lower()
    user_role = parse_role(role)
    if (
        not name
        or not valid_email(normalized_email)
        or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH
        or user_role is None
    ):
        return users_page(
            request,
            db,
            administrator,
            csrf_token,
            "Enter a name, valid email, password of at least 12 characters, and valid role.",
            400,
        )

    try:
        create_account(
            db,
            full_name=name,
            email=normalized_email,
            password=password,
            role=user_role,
            action="user.created",
            actor_user_id=administrator.id,
        )
        db.commit()
    except EmailAlreadyInUseError:
        db.rollback()
        return users_page(
            request, db, administrator, csrf_token, "That email address is already in use.", 409
        )
    except IntegrityError as error:
        db.rollback()
        if not is_duplicate_email_error(error):
            raise
        return users_page(
            request, db, administrator, csrf_token, "That email address is already in use.", 409
        )
    return RedirectResponse("/admin/users?created=1", status_code=303)


@router.post("/users/{user_id}", response_class=HTMLResponse, response_model=None)
def update_user(
    request: Request,
    user_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
    csrf_token: Annotated[str, Form()],
    full_name: Annotated[str, Form(max_length=200)],
    email: Annotated[str, Form(max_length=320)],
    role: Annotated[str, Form()],
    is_active: Annotated[str | None, Form()] = None,
    password: Annotated[str, Form(max_length=1024)] = "",
) -> HTMLResponse | RedirectResponse:
    user = db.get(User, user_id)
    if user is None:
        return users_page(request, db, administrator, csrf_token, "Account not found.", 404)

    name = full_name.strip()
    normalized_email = email.strip().lower()
    user_role = parse_role(role)
    active = is_active in {"on", "true", "1"}
    password_changed = bool(password)
    if (
        not name
        or not valid_email(normalized_email)
        or user_role is None
        or (password_changed and len(password) < MIN_PASSWORD_LENGTH)
    ):
        return users_page(
            request,
            db,
            administrator,
            csrf_token,
            "Enter a name, valid email, valid role, and any new password must be at least 12 characters.",
            400,
        )

    active_admins = db.scalars(
        select(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .order_by(User.id)
        .with_for_update()
    ).all()
    if (
        user.role == UserRole.ADMIN
        and user.is_active
        and (user_role != UserRole.ADMIN or not active)
        and len(active_admins) <= 1
    ):
        db.rollback()
        return users_page(
            request,
            db,
            administrator,
            csrf_token,
            "The last active administrator cannot be deactivated or demoted.",
            409,
        )

    previous_values = {
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
    }
    user.full_name = name
    user.email = normalized_email
    user.role = user_role
    user.is_active = active
    if password_changed:
        user.password_hash = hash_password(password)

    db.add(
        AuditLog(
            actor_user_id=administrator.id,
            action="user.updated",
            entity_type="user",
            entity_id=str(user.id),
            details={
                "before": previous_values,
                "after": {
                    "email": normalized_email,
                    "role": user_role.value,
                    "is_active": active,
                    "password_changed": password_changed,
                },
            },
        )
    )
    if not active or password_changed:
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if not is_duplicate_email_error(error):
            raise
        return users_page(
            request, db, administrator, csrf_token, "That email address is already in use.", 409
        )
    return RedirectResponse("/admin/users?updated=1", status_code=303)
