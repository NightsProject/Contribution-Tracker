from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.routes import (
    admin,
    auth,
    contributions,
    dashboard,
    expenses,
    payment_settings,
    recurring_expenses,
)

app = FastAPI(title=get_settings().app_name)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(contributions.router)
app.include_router(expenses.router)
app.include_router(payment_settings.router)
app.include_router(recurring_expenses.router)
app.include_router(admin.router)


@app.get("/", tags=["status"])
def root() -> RedirectResponse:
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/healthz", tags=["status"])
def health() -> dict[str, str]:
    return {"status": "ok"}
