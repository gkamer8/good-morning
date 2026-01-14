"""Admin health check routes and utilities."""

import asyncio
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from src.api.template_config import templates
from src.config import get_settings
from src.storage.minio_storage import get_minio_storage


settings = get_settings()
router = APIRouter()

# RSS Feeds to check (one per source to avoid too many requests)
RSS_FEEDS_TO_CHECK = {
    "BBC News": "http://feeds.bbci.co.uk/news/rss.xml",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Hacker News": "https://hnrss.org/frontpage",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
}

# External APIs to check
EXTERNAL_APIS_TO_CHECK = {
    "Wikipedia (This Day in History)": "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/1/1",
    "ZenQuotes (Quote of the Day)": "https://zenquotes.io/api/today",
    "icanhazdadjoke (Dad Jokes)": ("https://icanhazdadjoke.com/", {"Accept": "application/json"}),
    "Open-Meteo (Weather)": "https://api.open-meteo.com/v1/forecast?latitude=40.7&longitude=-74&current_weather=true",
    "Yahoo Finance (Market Data)": "https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=1d",
    "ESPN (Sports)": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}


async def check_url_health(name: str, url: str, headers: dict = None, timeout: float = 10.0) -> dict:
    """Check if a URL is accessible and responding."""
    start_time = time.time()
    try:
        default_headers = {"User-Agent": "MorningDrive/1.0 HealthCheck"}
        if headers:
            default_headers.update(headers)
        async with httpx.AsyncClient(timeout=timeout, headers=default_headers) as client:
            response = await client.get(url, follow_redirects=True)
            elapsed = time.time() - start_time
            return {
                "name": name,
                "url": url,
                "status": "ok" if response.status_code < 400 else "error",
                "status_code": response.status_code,
                "response_time_ms": int(elapsed * 1000),
                "error": None if response.status_code < 400 else f"HTTP {response.status_code}",
            }
    except httpx.TimeoutException:
        elapsed = time.time() - start_time
        return {
            "name": name,
            "url": url,
            "status": "timeout",
            "status_code": None,
            "response_time_ms": int(elapsed * 1000),
            "error": "Request timed out",
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "name": name,
            "url": url,
            "status": "error",
            "status_code": None,
            "response_time_ms": int(elapsed * 1000),
            "error": str(e)[:100],
        }


async def check_minio_health() -> dict:
    """Check MinIO storage connectivity."""
    start_time = time.time()
    try:
        storage = get_minio_storage()
        await storage.ensure_bucket_exists()
        await storage.list_files(prefix="")
        elapsed = time.time() - start_time
        return {
            "name": "MinIO Storage",
            "status": "ok",
            "response_time_ms": int(elapsed * 1000),
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "name": "MinIO Storage",
            "status": "error",
            "response_time_ms": int(elapsed * 1000),
            "error": str(e)[:100],
        }


async def check_anthropic_health() -> dict:
    """Check Anthropic API key validity (without making a real request)."""
    if not settings.anthropic_api_key:
        return {
            "name": "Anthropic API",
            "status": "not_configured",
            "response_time_ms": 0,
            "error": "API key not configured",
        }
    return {
        "name": "Anthropic API",
        "status": "configured",
        "response_time_ms": 0,
        "error": None,
    }


async def check_elevenlabs_health() -> dict:
    """Check ElevenLabs API connectivity."""
    if not settings.elevenlabs_api_key:
        return {
            "name": "ElevenLabs API",
            "status": "not_configured",
            "response_time_ms": 0,
            "error": "API key not configured",
        }
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": settings.elevenlabs_api_key}
            )
            elapsed = time.time() - start_time
            if response.status_code == 200:
                return {
                    "name": "ElevenLabs API",
                    "status": "ok",
                    "response_time_ms": int(elapsed * 1000),
                    "error": None,
                }
            elif response.status_code == 401:
                return {
                    "name": "ElevenLabs API",
                    "status": "error",
                    "response_time_ms": int(elapsed * 1000),
                    "error": "Invalid API key",
                }
            else:
                return {
                    "name": "ElevenLabs API",
                    "status": "error",
                    "response_time_ms": int(elapsed * 1000),
                    "error": f"HTTP {response.status_code}",
                }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "name": "ElevenLabs API",
            "status": "error",
            "response_time_ms": int(elapsed * 1000),
            "error": str(e)[:100],
        }


@router.get("/health")
async def admin_health_page(request: Request):
    """Admin health check page - shows status of all external dependencies."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Run all health checks in parallel
    rss_checks = [check_url_health(name, url) for name, url in RSS_FEEDS_TO_CHECK.items()]
    
    api_checks = []
    for name, config in EXTERNAL_APIS_TO_CHECK.items():
        if isinstance(config, tuple):
            url, headers = config
            api_checks.append(check_url_health(name, url, headers))
        else:
            api_checks.append(check_url_health(name, config))

    internal_checks = [
        check_minio_health(),
        check_anthropic_health(),
        check_elevenlabs_health(),
    ]

    # Execute all checks concurrently
    all_results = await asyncio.gather(
        *rss_checks,
        *api_checks,
        *internal_checks,
        return_exceptions=True
    )

    # Split results back into categories
    rss_results = all_results[:len(rss_checks)]
    api_results = all_results[len(rss_checks):len(rss_checks) + len(api_checks)]
    internal_results = all_results[len(rss_checks) + len(api_checks):]

    def normalize_result(result):
        if isinstance(result, Exception):
            return {
                "name": "Unknown",
                "status": "error",
                "response_time_ms": 0,
                "error": str(result)[:100],
            }
        return result

    rss_results = [normalize_result(r) for r in rss_results]
    api_results = [normalize_result(r) for r in api_results]
    internal_results = [normalize_result(r) for r in internal_results]

    # Calculate overall status
    all_statuses = [r.get("status", "error") for r in rss_results + api_results + internal_results]
    ok_count = sum(1 for s in all_statuses if s in ("ok", "configured"))
    warning_count = sum(1 for s in all_statuses if s in ("not_configured", "timeout"))
    error_count = sum(1 for s in all_statuses if s == "error")
    total = len(all_statuses)

    if error_count > 0:
        overall_status = "error"
        overall_text = f"{error_count} service(s) have errors"
    elif warning_count > 0:
        overall_status = "warning"
        overall_text = f"{warning_count} service(s) need attention"
    else:
        overall_status = "ok"
        overall_text = "All systems operational"

    return templates.TemplateResponse(
        request,
        "admin/health.html",
        {
            "active_page": "admin-health",
            "is_authenticated": True,
            "rss_results": rss_results,
            "api_results": api_results,
            "internal_results": internal_results,
            "overall_status": overall_status,
            "overall_text": overall_text,
            "ok_count": ok_count,
            "total_count": total,
            "last_checked": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
    )

