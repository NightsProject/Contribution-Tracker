from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title=get_settings().app_name)


@app.get("/", tags=["status"])
def root() -> dict[str, str]:
    return {"name": get_settings().app_name, "status": "foundation"}


@app.get("/healthz", tags=["status"])
def health() -> dict[str, str]:
    return {"status": "ok"}
