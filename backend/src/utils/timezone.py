"""Timezone utilities for consistent datetime handling across the app."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/New_York"


def get_user_now(timezone_str: str = None) -> datetime:
    """Get current datetime in user's timezone.

    Args:
        timezone_str: IANA timezone string (e.g., "America/New_York", "America/Los_Angeles")

    Returns:
        Timezone-aware datetime in user's local time
    """
    try:
        tz = ZoneInfo(timezone_str or DEFAULT_TIMEZONE)
    except Exception:
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    return datetime.now(tz)


def get_user_today(timezone_str: str = None) -> date:
    """Get today's date in user's timezone.

    Args:
        timezone_str: IANA timezone string

    Returns:
        Date object for today in user's local timezone
    """
    return get_user_now(timezone_str).date()


def get_timezone(timezone_str: str = None) -> ZoneInfo:
    """Get a ZoneInfo object for the given timezone string.

    Args:
        timezone_str: IANA timezone string

    Returns:
        ZoneInfo object, defaulting to America/New_York if invalid
    """
    try:
        return ZoneInfo(timezone_str or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)
