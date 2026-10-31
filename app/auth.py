import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole, UserSession
from app.security import hash_session_id, new_csrf_token, new_session_id

DbSession = Annotated[Session, Depends(get_db)]


def current_session(request: Request, db: DbSession) -> UserSession:
    session_id = request.cookies.get("session_id")
    if not session_id or len(session_id) != 64:
        raise login_redirect()
    if any(character not in "0123456789abcdef" for character in session_id):
        raise login_redirect()

    user_session = db.get(UserSession, hash_session_id(session_id))
    if user_session is None:
        raise login_redirect()

    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        db.delete(user_session)
        db.commit()
        raise login_redirect()
    return user_session


def signed_in_user(user_session: Annotated[UserSession, Depends(current_session)], db: DbSession) -> User:
    if user_session.user_id is None:
        raise login_redirect()
    user = db.get(User, user_session.user_id)
    if user is None or not user.is_active:
        db.delete(user_session)
        db.commit()
        raise login_redirect()
    return user


def admin_user(user: Annotated[User, Depends(signed_in_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


async def require_csrf(
    request: Request,
    user_session: Annotated[UserSession, Depends(current_session)],
) -> None:
    submitted_token = request.headers.get("x-csrf-token")
    if submitted_token is None:
        form = await request.form()
        submitted_token = str(form.get("csrf_token", ""))
    expected_token = str(user_session.data.get("csrf_token", ""))
    if not expected_token or not secrets.compare_digest(submitted_token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


def login_redirect() -> HTTPException:
    return HTTPException(status_code=303, headers={"Location": "/login"})


def new_user_session(user_id: UUID | None = None) -> tuple[UserSession, str]:
    session_id = new_session_id()
    user_session = UserSession(
        id=hash_session_id(session_id),
        user_id=user_id,
        data={"csrf_token": new_csrf_token()},
        expires_at=datetime.now(UTC) + timedelta(seconds=get_settings().session_max_age_seconds),
    )
    return user_session, session_id
