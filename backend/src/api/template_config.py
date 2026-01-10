"""Jinja2 template configuration for Morning Drive."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from src.version import VERSION

# Template configuration - separate module to avoid circular imports
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Add global context variables available in all templates
templates.env.globals["backend_version"] = VERSION
