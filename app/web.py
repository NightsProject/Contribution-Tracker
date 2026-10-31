from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import get_settings

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals["app_name"] = get_settings().app_name
