from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DbSession, admin_user, current_session, require_csrf, signed_in_user
from app.config import get_settings
from app.models import Expense, User, UserRole, UserSession
from app.services.accounting import (
    InsufficientFundsError,
    InvalidFinancialRecordError,
    get_pool_balance,
    post_expense,
)
from app.services.file_storage import InvalidImageError, private_image_path, store_private_image
from app.services.money import (
    MAX_AMOUNT_CENTAVOS,
    format_amount,
    format_amount_input,
    parse_amount_centavos,
)
from app.web import templates

router = APIRouter()
CsrfDependency = Annotated[None, Depends(require_csrf)]


def format_upload_size(size_bytes: int) -> str:
    megabyte = 1024 * 1024
    kilobyte = 1024
    if size_bytes % megabyte == 0:
        return f"{size_bytes // megabyte} MB"
    if size_bytes % kilobyte == 0:
        return f"{size_bytes // kilobyte} KB"
    return f"{size_bytes} bytes"


def expense_page(
    request: Request,
    db: Session,
    user: User,
    csrf_token: str,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    expenses = db.execute(
        select(Expense, User.full_name)
        .outerjoin(User, User.id == Expense.created_by)
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc(), Expense.id.desc())
    ).all()
    balance = get_pool_balance(db)
    return templates.TemplateResponse(
        request=request,
        name="expenses.html",
        context={
            "user": user,
            "csrf_token": csrf_token,
            "expenses": expenses,
            "error": error,
            "format_amount": format_amount,
            "available_balance": format_amount(balance.available_centavos),
            "max_amount_php": format_amount_input(MAX_AMOUNT_CENTAVOS),
            "max_upload_size": format_upload_size(get_settings().max_upload_size_bytes),
            "created": request.query_params.get("created") == "1",
        },
        status_code=status_code,
    )


@router.get("/expenses", response_class=HTMLResponse)
def expense_history(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(signed_in_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    return expense_page(request, db, user, user_session.data["csrf_token"])


@router.post("/admin/expenses", response_class=HTMLResponse, response_model=None)
async def create_expense(
    request: Request,
    db: DbSession,
    administrator: Annotated[User, Depends(admin_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
    _csrf: CsrfDependency,
    description: Annotated[str, Form(max_length=500)],
    category: Annotated[str, Form(max_length=100)],
    amount: Annotated[str, Form(max_length=32)],
    expense_date: Annotated[date, Form()],
    receipt: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse | RedirectResponse:
    amount_centavos = parse_amount_centavos(amount)
    if amount_centavos is None:
        return expense_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            "Enter a positive PHP amount with no more than two decimal places.",
            400,
        )
    if not description.strip() or len(description.strip()) > 500:
        return expense_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            "Expense description is required and must be 500 characters or fewer.",
            400,
        )
    if not category.strip() or len(category.strip()) > 100:
        return expense_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            "Expense category is required and must be 100 characters or fewer.",
            400,
        )

    receipt_key: str | None = None
    receipt_path: Path | None = None
    if receipt is not None and receipt.filename:
        contents = await receipt.read(get_settings().max_upload_size_bytes + 1)
        if len(contents) > get_settings().max_upload_size_bytes:
            return expense_page(
                request,
                db,
                administrator,
                user_session.data["csrf_token"],
                f"Receipt image exceeds the {format_upload_size(get_settings().max_upload_size_bytes)} upload limit.",
                413,
            )
        try:
            receipt_key, _, receipt_path = store_private_image(contents)
        except InvalidImageError as error:
            return expense_page(
                request,
                db,
                administrator,
                user_session.data["csrf_token"],
                str(error),
                400,
            )

    committed = False
    try:
        post_expense(
            db,
            actor_user_id=administrator.id,
            description=description,
            category=category,
            amount_centavos=amount_centavos,
            expense_date=expense_date,
            receipt_file_key=receipt_key,
        )
        committed = True
    except InsufficientFundsError as error:
        return expense_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            str(error),
            400,
        )
    except InvalidFinancialRecordError as error:
        return expense_page(
            request,
            db,
            administrator,
            user_session.data["csrf_token"],
            str(error),
            400,
        )
    finally:
        if not committed and receipt_path is not None:
            receipt_path.unlink(missing_ok=True)
    return RedirectResponse("/expenses?created=1", status_code=303)


@router.get("/expenses/{expense_id}/receipt")
def view_expense_receipt(
    expense_id: UUID,
    db: DbSession,
    _user: Annotated[User, Depends(signed_in_user)],
) -> FileResponse:
    expense = db.get(Expense, expense_id)
    if expense is None or expense.receipt_file_key is None:
        raise HTTPException(status_code=404, detail="Receipt image not found")
    file_path = private_image_path(expense.receipt_file_key)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Receipt image not found")
    media_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(file_path.suffix)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Receipt image not found")
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=f"receipt{file_path.suffix}",
        headers={"X-Content-Type-Options": "nosniff"},
    )
