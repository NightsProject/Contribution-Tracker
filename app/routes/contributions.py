from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DbSession, admin_user, current_session, require_csrf, signed_in_user
from app.config import get_settings
from app.models import AuditLog, Contribution, ContributionStatus, User, UserRole, UserSession
from app.services.file_storage import InvalidImageError, private_image_path, store_private_image
from app.services.accounting import (
    FinancialStateError,
    InsufficientFundsError,
    InvalidFinancialRecordError,
    reverse_contribution,
)
from app.services.contribution_service import (
    ContributionStateError,
    review_contribution,
    void_contribution,
)
from app.services.money import (
    MAX_AMOUNT_CENTAVOS,
    format_amount,
    format_amount_input,
    parse_amount_centavos,
)
from app.web import templates

router = APIRouter()
CsrfDependency = Annotated[None, Depends(require_csrf)]


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(ZoneInfo(get_settings().timezone)).strftime("%Y-%m-%d %H:%M")


def format_upload_size(size_bytes: int) -> str:
    megabyte = 1024 * 1024
    kilobyte = 1024
    if size_bytes % megabyte == 0:
        return f"{size_bytes // megabyte} MB"
    if size_bytes % kilobyte == 0:
        return f"{size_bytes // kilobyte} KB"
    return f"{size_bytes} bytes"


def list_user_contributions(db: Session, user_id: UUID) -> list[Contribution]:
    return db.scalars(
        select(Contribution)
        .where(Contribution.user_id == user_id)
        .order_by(Contribution.created_at.desc(), Contribution.id.desc())
    ).all()


def history_page(
    request: Request,
    user: User,
    csrf_token: str,
    contributions: list[Contribution],
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="contributions.html",
        context={
            "user": user,
            "csrf_token": csrf_token,
            "contributions": contributions,
            "error": error,
            "format_amount": format_amount,
            "format_timestamp": format_timestamp,
            "max_upload_size": format_upload_size(get_settings().max_upload_size_bytes),
            "max_amount_php": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "submitted": request.query_params.get("submitted") == "1",
        },
        status_code=status_code,
    )


@router.get("/contributions", response_class=HTMLResponse)
def contribution_history(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(signed_in_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    contributions = list_user_contributions(db, user.id)
    return history_page(request, user, user_session.data["csrf_token"], contributions)


@router.post("/contributions", response_class=HTMLResponse, response_model=None)
async def submit_contribution(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(signed_in_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: CsrfDependency,
    amount: Annotated[str, Form(max_length=32)],
    payment_reference: Annotated[str, Form(max_length=200)],
    payment_date: Annotated[date, Form()],
    proof: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse | RedirectResponse:
    normalized_reference = payment_reference.strip()
    amount_centavos = parse_amount_centavos(amount)
    if amount_centavos is None:
        return history_page(
            request,
            user,
            user_session.data["csrf_token"],
            list_user_contributions(db, user.id),
            "Enter a positive PHP amount with no more than two decimal places.",
            400,
        )
    if payment_date > datetime.now(ZoneInfo(get_settings().timezone)).date():
        return history_page(
            request,
            user,
            user_session.data["csrf_token"],
            list_user_contributions(db, user.id),
            "Payment date cannot be in the future.",
            400,
        )
    if not normalized_reference:
        return history_page(
            request,
            user,
            user_session.data["csrf_token"],
            list_user_contributions(db, user.id),
            "Payment reference is required.",
            400,
        )
    if len(normalized_reference) > 200:
        return history_page(
            request,
            user,
            user_session.data["csrf_token"],
            list_user_contributions(db, user.id),
            "Payment reference must be 200 characters or fewer.",
            400,
        )

    proof_key: str | None = None
    proof_path: Path | None = None
    if proof is not None and proof.filename:
        contents = await proof.read(get_settings().max_upload_size_bytes + 1)
        if len(contents) > get_settings().max_upload_size_bytes:
            return history_page(
                request,
                user,
                user_session.data["csrf_token"],
                list_user_contributions(db, user.id),
                f"Proof image exceeds the {format_upload_size(get_settings().max_upload_size_bytes)} upload limit.",
                413,
            )
        try:
            proof_key, _, proof_path = store_private_image(contents)
        except InvalidImageError as error:
            return history_page(
                request,
                user,
                user_session.data["csrf_token"],
                list_user_contributions(db, user.id),
                str(error),
                400,
            )
    committed = False
    try:
        contribution = Contribution(
            user_id=user.id,
            amount_centavos=amount_centavos,
            payment_reference=normalized_reference,
            payment_date=payment_date,
            proof_file_key=proof_key,
            status=ContributionStatus.PENDING,
        )
        db.add(contribution)
        db.flush()
        db.add(
            AuditLog(
                actor_user_id=user.id,
                action="contribution.submitted",
                entity_type="contribution",
                entity_id=str(contribution.id),
                details={
                    "amount_centavos": amount_centavos,
                    "payment_reference": normalized_reference,
                    "proof_attached": proof_key is not None,
                },
            )
        )
        db.commit()
        committed = True
    finally:
        if not committed and proof_path is not None:
            proof_path.unlink(missing_ok=True)
    return RedirectResponse("/contributions?submitted=1", status_code=303)


@router.get("/contributions/{contribution_id}/proof")
def view_contribution_proof(
    contribution_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(signed_in_user)],
) -> FileResponse:
    contribution = db.get(Contribution, contribution_id)
    if contribution is None or contribution.proof_file_key is None:
        raise HTTPException(status_code=404, detail="Proof image not found")
    if user.role != UserRole.ADMIN and contribution.user_id != user.id:
        raise HTTPException(status_code=404, detail="Proof image not found")
    file_path = private_image_path(contribution.proof_file_key)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Proof image not found")
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(file_path.suffix)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Proof image not found")
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=f"proof{file_path.suffix}",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/admin/contributions/pending", response_class=HTMLResponse)
def pending_contributions(
    request: Request,
    db: DbSession,
    administrator: Annotated[User, Depends(admin_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    pending = db.execute(
        select(Contribution, User)
        .join(User, User.id == Contribution.user_id)
        .where(Contribution.status == ContributionStatus.PENDING)
        .order_by(Contribution.created_at, Contribution.id)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="pending_contributions.html",
        context={
            "administrator": administrator,
            "csrf_token": user_session.data["csrf_token"],
            "pending": pending,
            "format_amount": format_amount,
            "format_timestamp": format_timestamp,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/contributions/{contribution_id}/approve")
def approve_contribution(
    contribution_id: UUID,
    db: DbSession,
    administrator: Annotated[User, Depends(admin_user)],
    _csrf: CsrfDependency,
) -> RedirectResponse:
    try:
        review_contribution(
            db,
            contribution_id=contribution_id,
            administrator_id=administrator.id,
            approved=True,
        )
    except ContributionStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse("/admin/contributions/pending?reviewed=1", status_code=303)


@router.post("/admin/contributions/{contribution_id}/reject")
def reject_contribution(
    contribution_id: UUID,
    db: DbSession,
    administrator: Annotated[User, Depends(admin_user)],
    _csrf: CsrfDependency,
    reason: Annotated[str, Form(max_length=1000)],
) -> RedirectResponse:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise HTTPException(status_code=400, detail="A rejection reason is required.")
    try:
        review_contribution(
            db,
            contribution_id=contribution_id,
            administrator_id=administrator.id,
            approved=False,
            rejection_reason=normalized_reason,
        )
    except ContributionStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse("/admin/contributions/pending?reviewed=1", status_code=303)


@router.post("/admin/contributions/{contribution_id}/void")
def void_pending_contribution(
    contribution_id: UUID,
    db: DbSession,
    administrator: Annotated[User, Depends(admin_user)],
    _csrf: CsrfDependency,
    reason: Annotated[str, Form(max_length=1000)],
) -> RedirectResponse:
    try:
        void_contribution(
            db,
            contribution_id=contribution_id,
            administrator_id=administrator.id,
            reason=reason,
        )
    except InvalidFinancialRecordError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ContributionStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse("/dashboard?transaction_action=voided", status_code=303)


@router.post("/admin/contributions/{contribution_id}/refund")
def refund_approved_contribution(
    contribution_id: UUID,
    db: DbSession,
    administrator: Annotated[User, Depends(admin_user)],
    _csrf: CsrfDependency,
    reason: Annotated[str, Form(max_length=1000)],
) -> RedirectResponse:
    try:
        reverse_contribution(
            db,
            contribution_id=contribution_id,
            actor_user_id=administrator.id,
            reason=reason,
        )
    except InvalidFinancialRecordError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (FinancialStateError, InsufficientFundsError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return RedirectResponse("/dashboard?transaction_action=refunded", status_code=303)
