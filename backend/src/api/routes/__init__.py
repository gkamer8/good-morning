"""API route handlers."""

from fastapi import APIRouter

from .briefings import router as briefings_router
from .music import router as music_router
from .schedule import router as schedule_router
from .settings import router as settings_router
from .voices import router as voices_router


router = APIRouter()

# Include all sub-routers
router.include_router(briefings_router, tags=["briefings"])
router.include_router(settings_router, tags=["settings"])
router.include_router(schedule_router, tags=["schedule"])
router.include_router(voices_router, tags=["voices"])
router.include_router(music_router, tags=["music"])

