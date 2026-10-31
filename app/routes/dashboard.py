from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import current_session, signed_in_user
from app.models import User, UserSession
from app.web import templates

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: Annotated[User, Depends(signed_in_user)],
    user_session: Annotated[UserSession, Depends(current_session)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": user, "csrf_token": user_session.data["csrf_token"]},
    )
