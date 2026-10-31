from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes import (
    admin,
    auth,
    contributions,
    dashboard,
    expenses,
    payment_settings,
    recurring_expenses,
    trash,
)

app = FastAPI(title=get_settings().app_name)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'; img-src 'self'; "
        "style-src 'self'; script-src 'none'",
    )
    if get_settings().session_cookie_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(contributions.router)
app.include_router(expenses.router)
app.include_router(payment_settings.router)
app.include_router(recurring_expenses.router)
app.include_router(admin.router)
app.include_router(trash.router)


@app.get("/", tags=["status"])
def root() -> RedirectResponse:
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/healthz", tags=["status"])
def health() -> dict[str, str]:
    return {"status": "ok"}
