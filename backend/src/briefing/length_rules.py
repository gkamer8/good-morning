"""Consolidated length rules for briefing generation.

This module provides a single source of truth for all implications
of the briefing length setting (short vs long).
"""

from dataclasses import dataclass
from typing import Optional

from src.api.schemas import LengthMode


@dataclass(frozen=True)
class LengthRules:
    """All rules and limits that vary based on briefing length.
    
    Attributes:
        # Content limits
        news_stories_per_source: Number of stories to fetch per news outlet
        history_events: Number of "This Day in History" events to include
        finance_movers_limit: Number of top gainers/losers to show (None = all)
        sports_favorite_teams_only: If True, only show favorite teams' games
        
        # Script generation
        target_duration_minutes: Target audio duration
        target_word_count: Approximate word count for the script
        deep_dive_count: Number of stories to research in depth (when enabled)
    """
    
    # Content gathering limits
    news_stories_per_source: int
    history_events: int
    finance_movers_limit: Optional[int]  # None means all (5+5)
    sports_favorite_teams_only: bool
    
    # Script generation targets
    target_duration_minutes: int
    target_word_count: int
    
    # Deep dive research
    deep_dive_count: int


# Central mapping of length mode to all its rules
LENGTH_RULES: dict[LengthMode, LengthRules] = {
    LengthMode.SHORT: LengthRules(
        # Content: minimal, focused
        news_stories_per_source=1,
        history_events=1,
        finance_movers_limit=1,  # 1 gainer + 1 loser
        sports_favorite_teams_only=True,
        # Script: ~5 minutes
        target_duration_minutes=5,
        target_word_count=1000,
        # Deep dive: 1 story when enabled
        deep_dive_count=1,
    ),
    LengthMode.LONG: LengthRules(
        # Content: comprehensive
        news_stories_per_source=2,
        history_events=2,
        finance_movers_limit=None,  # All movers (5+5)
        sports_favorite_teams_only=False,
        # Script: ~10 minutes
        target_duration_minutes=10,
        target_word_count=2000,
        # Deep dive: 2 stories when enabled
        deep_dive_count=2,
    ),
}


