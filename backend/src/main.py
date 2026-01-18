"""Morning Drive - AI-powered morning briefing service."""

from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file before any other imports that might use env vars
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.admin import router as admin_router
from src.api.auth_routes import router as auth_router
from src.api.routes import router
from src.api.website import router as website_router
from src.config import get_settings
from src.scheduler import setup_scheduler
from src.storage.database import init_db
from src.storage.minio_storage import get_minio_storage
from src.version import VERSION


# Global scheduler reference
_scheduler = None


def get_scheduler():
    """Get the global scheduler instance."""
    return _scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _scheduler
    settings = get_settings()

    # Initialize database
    await init_db()

    # Initialize MinIO storage bucket
    try:
        storage = get_minio_storage()
        await storage.ensure_bucket_exists()
    except Exception as e:
        print(f"Warning: Could not initialize MinIO storage: {e}")

    # Mount static files for CSS/JS assets
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

    # Start the background scheduler
    _scheduler = await setup_scheduler()
    if _scheduler:
        _scheduler.start()
        print("Background scheduler started")

    yield

    # Cleanup on shutdown
    if _scheduler:
        _scheduler.shutdown()
        print("Background scheduler stopped")


app = FastAPI(
    title="Morning Drive",
    description="AI-powered personalized morning briefing service",
    version=VERSION,
    lifespan=lifespan,
    docs_url=None,  # Disable default docs, we use custom template
    redoc_url=None,  # Disable ReDoc
)

# CORS middleware for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# Include auth routes
app.include_router(auth_router, prefix="/api")

# Include admin routes
app.include_router(admin_router, prefix="/admin")

# Include public website routes (home page, docs)
app.include_router(website_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "morning-drive", "version": VERSION}


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
