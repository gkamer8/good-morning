"""Error handling for briefing generation.

This module provides:
- BriefingGenerationError: Exception to raise during briefing generation
- catch_generation_errors: Decorator that catches and logs these errors
- update_briefing_status: Helper to update briefing status in the database
"""

import functools
from typing import overload, Awaitable, Callable, Concatenate, Optional, ParamSpec, TypeVar

from sqlalchemy import select

from src.api.schemas import BriefingStatus
from src.storage.database import Briefing, async_session

P = ParamSpec("P")
T = TypeVar("T")

# Type alias for fallback functions - they receive the same args as the wrapped function
FallbackFn = Callable[P, T]

BriefingId = int


class RecoverableException(Exception):
    """
    A recoverable exception is an exception that caries a return value
    to be used instead of the fallback_content value.
    """
    def __init__(self, fallback_content) -> None:
        self.fallback_content = fallback_content
        super().__init__()


class GenerationCanceled(Exception):
    """Custom exception to raise if generation is canceled"""
    def __init__(self, phase: BriefingStatus) -> None:
        self.phase = phase
        super().__init__()


async def update_briefing_status(briefing_id: BriefingId, status: BriefingStatus):
    """Update the status of a briefing in the database."""
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if briefing:
            briefing.status = status.value
            await session.commit()


async def add_generation_error(
    briefing_id: BriefingId,
    function_name: str,
    recoverable: bool,
    fallback_content: Optional[str] = None,
):
    """Add an error to the briefing's error list."""
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if briefing:
            errors = briefing.generation_errors or []
            errors.append({
                "function_name": function_name,
                "recoverable": recoverable,
                "fallback_content": fallback_content,
            })
            briefing.generation_errors = errors
            await session.commit()


@overload
def catch_async_generation_errors(
    fallback_fn: None = None,
) -> Callable[[Callable[Concatenate[BriefingId, P], Awaitable[T]]], Callable[Concatenate[BriefingId, P], Awaitable[T]]]: ...

@overload
def catch_async_generation_errors(
    fallback_fn: Callable[P, Awaitable[T]],
) -> Callable[[Callable[Concatenate[BriefingId, P], Awaitable[T]]], Callable[Concatenate[BriefingId, P], Awaitable[T]]]: ...

def catch_async_generation_errors(
    fallback_fn: Callable[P, Awaitable[T]] | None = None,
) -> Callable[[Callable[Concatenate[BriefingId, P], Awaitable[T]]], Callable[Concatenate[BriefingId, P], Awaitable[T | None]]]:
    """
    Decorator to catch BriefingGenerationError and log it to the briefing.

    If fallback_fn is not None, the failure of the function is treated as
    recoverable. The fallback function is called with the same arguments as
    the wrapped function, and its return value is used as the result.

    If a RecoverableException is raised, the error is treated as recoverable
    with the exception's fallback content value being returned, no matter
    what fallback_fn was originally defined.
    """
    def decorator(func: Callable[Concatenate[BriefingId, P], Awaitable[T]]) -> Callable[Concatenate[BriefingId, P], Awaitable[T | None]]:
        @functools.wraps(func)
        async def wrapper(briefing_id: BriefingId, *args: P.args, **kwargs: P.kwargs) -> T | None:
            try:
                return await func(briefing_id, *args, **kwargs)
            except RecoverableException as e:
                print(f"[Briefing {briefing_id}] {func.__name__} error: {e}")
                await add_generation_error(
                    briefing_id,
                    func.__name__,
                    True,
                    e.fallback_content,
                )
                return e.fallback_content
            except Exception as e:
                # Could still be recoverable if fallback_fn is set
                print(f"[Briefing {briefing_id}] {func.__name__} error: {e}")
                recoverable = fallback_fn is not None
                if recoverable:
                    fallback_content = await fallback_fn(*args, **kwargs)  # Added await
                else:
                    fallback_content = None
                await add_generation_error(
                    briefing_id,
                    func.__name__,
                    recoverable,
                    fallback_content,
                )
                if recoverable:
                    return fallback_content
                # Error is not recoverable
                await update_briefing_status(briefing_id, BriefingStatus.FAILED)
                raise

        return wrapper
    return decorator