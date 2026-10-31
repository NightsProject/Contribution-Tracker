from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select

from app.auth import DbSession, admin_user, current_session, require_csrf
from app.models import (
    AuditLog,
    User,
    UserRole,
    UserSession,
)
from app.models.common import utc_now
from app.web import templates

router = APIRouter(prefix="/admin")
AdminDependency = Annotated[User, Depends(admin_user)]
CsrfDependency = Annotated[None, Depends(require_csrf)]


@router.get("/trash", response_class=HTMLResponse)
def view_trash(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    accounts = db.scalars(
        select(User)
        .where(User.trashed_at.is_not(None))
        .order_by(User.trashed_at.desc(), User.id)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_trash.html",
        context={
            "administrator": administrator,
            "csrf_token": user_session.data["csrf_token"],
            "accounts": accounts,
        },
    )


@router.post("/trash/accounts/{record_id}")
def trash_record(
    record_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
) -> RedirectResponse:
    now = utc_now()
    account = db.get(User, record_id)
    if account is None or account.trashed_at is not None:
        raise HTTPException(status_code=404, detail="Account not found.")
    if account.id == administrator.id:
        raise HTTPException(status_code=409, detail="You cannot trash your own administrator account.")
    if account.role == UserRole.ADMIN and account.is_active:
        active_admins = db.scalars(
            select(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        ).all()
        if len(active_admins) <= 1:
            raise HTTPException(
                status_code=409,
                detail="The last active administrator cannot be moved to trash.",
            )
    account.is_active = False
    account.trashed_at = now
    account.updated_at = now
    db.execute(delete(UserSession).where(UserSession.user_id == account.id))
    db.add(
        AuditLog(
            actor_user_id=administrator.id,
            action="user.trashed",
            entity_type="user",
            entity_id=str(account.id),
            details={"email": account.email},
        )
    )

    db.commit()
    return RedirectResponse("/admin/users?trashed=1", status_code=303)


@router.post("/trash/accounts/{record_id}/restore")
def restore_record(
    record_id: UUID,
    db: DbSession,
    administrator: AdminDependency,
    _csrf: CsrfDependency,
) -> RedirectResponse:
    record = db.get(User, record_id)
    if record is None or record.trashed_at is None:
        raise HTTPException(status_code=404, detail="Trash item not found.")
    record.trashed_at = None
    record.updated_at = utc_now()
    db.add(
        AuditLog(
            actor_user_id=administrator.id,
            action="user.restored_from_trash",
            entity_type="user",
            entity_id=str(record.id),
            details={"is_active": record.is_active},
        )
    )

    db.commit()
    return RedirectResponse("/admin/users?restored=1", status_code=303)
