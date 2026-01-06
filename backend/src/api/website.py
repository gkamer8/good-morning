"""Public website routes for Morning Drive."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from src.api.template_config import templates

router = APIRouter()


@router.get("/")
async def home_page(request: Request):
    """Home page with overview and quick links."""
    return templates.TemplateResponse(
        request,
        "pages/home.html",
        {"active_page": "home", "is_authenticated": False},
    )


@router.get("/docs/getting-started")
async def docs_getting_started(request: Request):
    """Getting started documentation page."""
    return templates.TemplateResponse(
        request,
        "pages/docs/getting-started.html",
        {
            "active_page": "docs",
            "active_doc": "getting-started",
            "page_title": "Getting Started",
            "is_authenticated": False,
        },
    )


@router.get("/docs/deployment")
async def docs_deployment(request: Request):
    """Deployment documentation page."""
    return templates.TemplateResponse(
        request,
        "pages/docs/deployment.html",
        {
            "active_page": "docs",
            "active_doc": "deployment",
            "page_title": "Deployment",
            "is_authenticated": False,
        },
    )


@router.get("/docs/development")
async def docs_development(request: Request):
    """Development documentation page."""
    return templates.TemplateResponse(
        request,
        "pages/docs/development.html",
        {
            "active_page": "docs",
            "active_doc": "development",
            "page_title": "Development",
            "is_authenticated": False,
        },
    )


@router.get("/docs")
async def docs_index():
    """Redirect /docs to getting started page."""
    return RedirectResponse(url="/docs/getting-started", status_code=302)


@router.get("/api/docs")
async def api_docs_page(request: Request):
    """Interactive API documentation with Swagger UI."""
    return templates.TemplateResponse(
        request,
        "pages/api-docs.html",
        {"active_page": "api", "is_authenticated": False},
    )
