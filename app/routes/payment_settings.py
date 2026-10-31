from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.auth import DbSession, admin_user, current_session, require_csrf, signed_in_user
from app.config import get_settings
from app.models import AuditLog, PaymentSettings, User, UserSession
from app.services.file_storage import InvalidImageError, private_image_path, store_private_image
from app.web import templates

router = APIRouter(prefix="/admin/payment-settings")
AdminDependency = Annotated[User, Depends(admin_user)]
CsrfDependency = Annotated[None, Depends(require_csrf)]


def settings_page(
    request: Request,
    settings: PaymentSettings,
    administrator: User,
    csrf_token: str,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    upload_limit = get_settings().max_upload_size_bytes
    upload_limit_label = (
        f"{upload_limit // (1024 * 1024)} MB"
        if upload_limit % (1024 * 1024) == 0
        else f"{upload_limit // 1024} KB"
        if upload_limit % 1024 == 0
        else f"{upload_limit} bytes"
    )
    return templates.TemplateResponse(
        request=request,
        name="payment_settings.html",
        context={
            "settings": settings,
            "administrator": administrator,
            "csrf_token": csrf_token,
            "error": error,
            "saved": request.query_params.get("saved") == "1",
            "max_upload_size": upload_limit_label,
        },
        status_code=status_code,
    )


def get_or_create_settings(db: Session) -> PaymentSettings:
    dialect = db.get_bind().dialect.name
    table = PaymentSettings.__table__
    if dialect == "postgresql":
        db.execute(
            postgresql_insert(table).values(id=1).on_conflict_do_nothing(index_elements=[table.c.id])
        )
    elif dialect == "sqlite":
        db.execute(
            sqlite_insert(table).values(id=1).on_conflict_do_nothing(index_elements=[table.c.id])
        )
    settings = db.scalar(select(PaymentSettings).where(PaymentSettings.id == 1).with_for_update())
    if settings is None:
        settings = PaymentSettings(id=1)
        db.add(settings)
        db.flush()
    return settings


@router.get("", response_class=HTMLResponse)
def manage_payment_settings(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    settings = get_or_create_settings(db)
    db.commit()
    return settings_page(
        request,
        settings,
        administrator,
        user_session.data["csrf_token"],
    )


@router.post("", response_class=HTMLResponse, response_model=None)
async def update_payment_settings(
    request: Request,
    db: DbSession,
    administrator: AdminDependency,
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: CsrfDependency,
    payment_method: Annotated[str, Form(max_length=100)] = "",
    account_name: Annotated[str, Form(max_length=200)] = "",
    account_identifier: Annotated[str, Form(max_length=200)] = "",
    instructions: Annotated[str, Form(max_length=10000)] = "",
    remove_qr: Annotated[str | None, Form()] = None,
    qr_image: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse | RedirectResponse:
    settings = get_or_create_settings(db)
    payment_method = payment_method.strip()
    account_name = account_name.strip()
    account_identifier = account_identifier.strip()
    instructions = instructions.strip()
    qr_key = settings.qr_file_key
    qr_path: Path | None = None

    if qr_image is not None and qr_image.filename:
        contents = await qr_image.read(get_settings().max_upload_size_bytes + 1)
        if len(contents) > get_settings().max_upload_size_bytes:
            return settings_page(
                request,
                settings,
                administrator,
                user_session.data["csrf_token"],
                "QR image exceeds the configured upload limit.",
                413,
            )
        try:
            qr_key, _, qr_path = store_private_image(contents)
        except InvalidImageError as error:
            return settings_page(
                request,
                settings,
                administrator,
                user_session.data["csrf_token"],
                str(error),
                400,
            )
    elif remove_qr == "on":
        qr_key = None

    previous_values = {
        "payment_method": settings.payment_method,
        "account_name": settings.account_name,
        "account_identifier": settings.account_identifier,
        "instructions": settings.instructions,
        "qr_file_key": settings.qr_file_key,
    }
    committed = False
    try:
        settings.payment_method = payment_method or None
        settings.account_name = account_name or None
        settings.account_identifier = account_identifier or None
        settings.instructions = instructions or None
        settings.qr_file_key = qr_key
        settings.updated_by = administrator.id
        db.add(
            AuditLog(
                actor_user_id=administrator.id,
                action="payment_settings.updated",
                entity_type="payment_settings",
                entity_id="1",
                details={
                    "previous": previous_values,
                    "payment_method": settings.payment_method,
                    "account_name": settings.account_name,
                    "account_identifier": settings.account_identifier,
                    "instructions": settings.instructions,
                    "qr_file_key": settings.qr_file_key,
                },
            )
        )
        db.commit()
        committed = True
    finally:
        if not committed:
            db.rollback()
            if qr_path is not None:
                qr_path.unlink(missing_ok=True)
    return RedirectResponse("/admin/payment-settings?saved=1", status_code=303)


@router.get("/qr")
def view_payment_qr(
    db: DbSession,
    _user: Annotated[User, Depends(signed_in_user)],
) -> FileResponse:
    settings = db.get(PaymentSettings, 1)
    if settings is None or settings.qr_file_key is None:
        raise HTTPException(status_code=404, detail="Payment QR image not found.")
    file_path = private_image_path(settings.qr_file_key)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Payment QR image not found.")
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(file_path.suffix)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Payment QR image not found.")
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=f"payment-qr{file_path.suffix}",
        headers={"X-Content-Type-Options": "nosniff"},
    )
