"""Jinja2 template configuration for Morning Drive."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

# Template configuration - separate module to avoid circular imports
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
