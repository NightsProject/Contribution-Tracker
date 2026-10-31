from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.auth import DbSession, current_session, new_user_session, require_csrf
from app.config import get_settings
from app.database import get_db
from app.models import LoginAttempt, User, UserRole, UserSession
from app.security import (
    DUMMY_PASSWORD_HASH,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    hash_session_id,
    login_attempt_key,
    needs_rehash,
    valid_email,
    verify_password,
)
from app.services.bootstrap import (
    AdminAlreadyExistsError,
    create_initial_admin,
    has_admin_account,
)
from app.services.accounts import EmailAlreadyInUseError, create_account
from app.web import templates

router = APIRouter()
MAX_FAILED_LOGINS = 5
LOGIN_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(minutes=15)
EmailForm = Annotated[str, Form(max_length=320)]
PasswordForm = Annotated[str, Form(max_length=1024)]
PasswordConfirmationForm = Annotated[str, Form(max_length=1024)]


def set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "session_id",
        session_id,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(
        "session_id",
        httponly=True,
        secure=get_settings().session_cookie_secure,
        samesite="lax",
        path="/",
    )


def active_session(user_session: UserSession) -> bool:
    expiry = user_session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return expiry > datetime.now(UTC)


def public_form_session(
    request: Request,
    db: Session,
    *,
    authenticated_redirect: str,
) -> tuple[UserSession, str] | RedirectResponse:
    session_id = request.cookies.get("session_id")
    user_session = None
    if (
        session_id is not None
        and len(session_id) == 64
        and all(character in "0123456789abcdef" for character in session_id)
    ):
        user_session = db.get(UserSession, hash_session_id(session_id))
    if user_session is not None and not active_session(user_session):
        db.delete(user_session)
        db.commit()
        user_session = None

    if user_session is not None and user_session.user_id is not None:
        user = db.get(User, user_session.user_id)
        if user is not None and user.is_active:
            return RedirectResponse(authenticated_redirect, status_code=303)
        db.delete(user_session)
        db.commit()
        user_session = None

    if user_session is None:
        user_session, session_id = new_user_session()
        db.add(user_session)
        db.commit()
    else:
        session_id = request.cookies.get("session_id", "")
    return user_session, session_id


@router.get("/login", response_class=HTMLResponse, name="login", response_model=None)
def login_page(request: Request, db: DbSession) -> HTMLResponse | RedirectResponse:
    session = public_form_session(request, db, authenticated_redirect="/")
    if isinstance(session, RedirectResponse):
        return session
    user_session, session_id = session

    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "csrf_token": user_session.data["csrf_token"],
            "error": None,
            "setup_available": not has_admin_account(db),
        },
    )
    set_session_cookie(response, session_id)
    return response


@router.get("/setup", response_class=HTMLResponse, name="setup", response_model=None)
def setup_page(request: Request, db: DbSession) -> HTMLResponse | RedirectResponse:
    if has_admin_account(db):
        return RedirectResponse("/login", status_code=303)

    session = public_form_session(request, db, authenticated_redirect="/dashboard")
    if isinstance(session, RedirectResponse):
        return session
    user_session, session_id = session

    response = templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={
            "csrf_token": user_session.data["csrf_token"],
            "error": None,
            "full_name": "",
            "email": "",
        },
    )
    set_session_cookie(response, session_id)
    return response


@router.get("/signup", response_class=HTMLResponse, name="signup", response_model=None)
def signup_page(request: Request, db: DbSession) -> HTMLResponse | RedirectResponse:
    session = public_form_session(request, db, authenticated_redirect="/dashboard")
    if isinstance(session, RedirectResponse):
        return session
    user_session, session_id = session
    response = templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={
            "csrf_token": user_session.data["csrf_token"],
            "error": None,
            "full_name": "",
            "email": "",
        },
    )
    set_session_cookie(response, session_id)
    return response


@router.post("/signup", response_class=HTMLResponse, response_model=None)
def signup(
    request: Request,
    db: DbSession,
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: Annotated[None, Depends(require_csrf)],
    full_name: Annotated[str, Form(max_length=200)],
    email: EmailForm,
    password: PasswordForm,
    password_confirmation: PasswordConfirmationForm,
) -> HTMLResponse | RedirectResponse:
    if user_session.user_id is not None:
        return RedirectResponse("/dashboard", status_code=303)

    name = full_name.strip()
    normalized_email = email.strip().lower()
    if (
        not name
        or not valid_email(normalized_email)
        or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH
        or password != password_confirmation
    ):
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={
                "csrf_token": user_session.data["csrf_token"],
                "error": (
                    "Enter a name, valid email, matching passwords, and a password "
                    f"between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."
                ),
                "full_name": name,
                "email": normalized_email,
            },
            status_code=400,
        )

    try:
        user = create_account(
            db,
            full_name=name,
            email=normalized_email,
            password=password,
            role=UserRole.USER,
            action="user.signed_up",
        )
    except EmailAlreadyInUseError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={
                "csrf_token": user_session.data["csrf_token"],
                "error": "Unable to create an account with those details.",
                "full_name": name,
                "email": normalized_email,
            },
            status_code=400,
        )

    db.delete(user_session)
    authenticated_session, session_id = new_user_session(user.id)
    db.add(authenticated_session)
    db.commit()
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, session_id)
    return response


@router.post("/setup", response_class=HTMLResponse, response_model=None)
def create_first_admin(
    request: Request,
    db: DbSession,
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: Annotated[None, Depends(require_csrf)],
    full_name: Annotated[str, Form(max_length=200)],
    email: EmailForm,
    password: PasswordForm,
    password_confirmation: PasswordConfirmationForm,
) -> HTMLResponse | RedirectResponse:
    if user_session.user_id is not None:
        return RedirectResponse("/dashboard", status_code=303)

    name = full_name.strip()
    normalized_email = email.strip().lower()
    if (
        not name
        or not valid_email(normalized_email)
        or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH
        or password != password_confirmation
    ):
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={
                "csrf_token": user_session.data["csrf_token"],
                "error": (
                    "Enter a name, valid email, matching passwords, and a password "
                    f"between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."
                ),
                "full_name": name,
                "email": normalized_email,
            },
            status_code=400,
        )

    try:
        administrator = create_initial_admin(
            db,
            full_name=name,
            email=normalized_email,
            password=password,
        )
    except AdminAlreadyExistsError:
        db.rollback()
        return RedirectResponse("/login", status_code=303)
    except EmailAlreadyInUseError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={
                "csrf_token": user_session.data["csrf_token"],
                "error": "That email address is already in use.",
                "full_name": name,
                "email": normalized_email,
            },
            status_code=409,
        )

    db.delete(user_session)
    authenticated_session, session_id = new_user_session(administrator.id)
    db.add(authenticated_session)
    db.commit()
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, session_id)
    return response


def is_login_locked(db: Session, key: str, now: datetime) -> bool:
    attempt = db.get(LoginAttempt, key)
    if attempt is None:
        return False
    lock_until = attempt.locked_until
    if lock_until is not None:
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=UTC)
        if lock_until > now:
            return True

    window_start = attempt.window_started_at
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=UTC)
    return window_start > now - LOGIN_WINDOW and attempt.failed_attempts >= MAX_FAILED_LOGINS


def record_failed_login(db: Session, key: str, now: datetime) -> None:
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        insert = postgresql_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise RuntimeError(f"Login throttling does not support database dialect {dialect!r}")
    table = LoginAttempt.__table__
    statement = insert(table).values(
        key=key,
        failed_attempts=1,
        window_started_at=now,
        locked_until=None,
    )
    reset_window = table.c.window_started_at <= now - LOGIN_WINDOW
    next_count = case(
        (reset_window, 1),
        else_=table.c.failed_attempts + 1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.key],
        set_={
            "failed_attempts": next_count,
            "window_started_at": case(
                (reset_window, now), else_=table.c.window_started_at
            ),
            "locked_until": case(
                (reset_window, None),
                (next_count >= MAX_FAILED_LOGINS, now + LOCKOUT_DURATION),
                else_=table.c.locked_until,
            ),
        },
    )
    db.execute(statement)
    db.commit()


@router.post("/login", response_class=HTMLResponse, response_model=None)
def login(
    request: Request,
    db: DbSession,
    email: EmailForm,
    password: PasswordForm,
    _csrf: Annotated[None, Depends(require_csrf)],
) -> HTMLResponse | RedirectResponse:
    normalized_email = email.strip().lower()
    user_session = current_session(request, db)
    now = datetime.now(UTC)
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.window_started_at <= now - LOGIN_WINDOW,
            or_(LoginAttempt.locked_until.is_(None), LoginAttempt.locked_until <= now),
        )
    )
    db.commit()
    user = db.scalar(select(User).where(User.email == normalized_email))
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password, password_hash)
    attempt_key = login_attempt_key(normalized_email, request.client.host if request.client else "")

    if is_login_locked(db, attempt_key, now):
        error = "Unable to sign in. Check your credentials or try again later."
    elif user is None or not user.is_active or not password_valid:
        record_failed_login(db, attempt_key, now)
        error = "Unable to sign in. Check your credentials or try again later."
    else:
        db.delete(user_session)
        authenticated_session, session_id = new_user_session(user.id)
        db.add(authenticated_session)
        db.execute(delete(LoginAttempt).where(LoginAttempt.key == attempt_key))
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        db.commit()
        response = RedirectResponse("/", status_code=303)
        set_session_cookie(response, session_id)
        return response

    response = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "csrf_token": user_session.data["csrf_token"],
            "error": error,
            "setup_available": not has_admin_account(db),
        },
        status_code=400,
    )
    return response


@router.post("/logout")
def logout(
    user_session: Annotated[UserSession, Depends(current_session)],
    db: DbSession,
    _csrf: Annotated[None, Depends(require_csrf)],
) -> RedirectResponse:
    db.delete(user_session)
    db.commit()
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response
