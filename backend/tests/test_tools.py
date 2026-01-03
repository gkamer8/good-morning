"""Tests for data fetching tools."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from src.tools.news_tools import (
    NewsArticle,
    fetch_rss_feed,
    format_news_for_agent,
    RSS_FEEDS,
)
from src.tools.fun_tools import (
    HistoricalEvent,
    Quote,
    DadJoke,
    fetch_quote_of_the_day,
    fetch_dad_joke,
    format_fun_content_for_agent,
)
from src.tools.music_tools import (
    MusicPieceInfo,
    format_music_for_agent,
)


class TestNewsTools:
    """Tests for news fetching tools."""

    def test_rss_feeds_structure(self):
        """Verify RSS_FEEDS has expected sources."""
        assert "bbc" in RSS_FEEDS
        assert "npr" in RSS_FEEDS
        assert "nyt" in RSS_FEEDS
        # Reuters should be removed (broken)
        assert "reuters" not in RSS_FEEDS

    def test_bbc_has_required_topics(self):
        """Verify BBC feeds have required topics."""
        assert "top" in RSS_FEEDS["bbc"]
        assert "world" in RSS_FEEDS["bbc"]
        assert "technology" in RSS_FEEDS["bbc"]
        assert "business" in RSS_FEEDS["bbc"]

    def test_format_news_for_agent_empty(self):
        """Test formatting with no articles."""
        result = format_news_for_agent([])
        assert result == "No news articles available."

    def test_format_news_for_agent_with_articles(self):
        """Test formatting with articles."""
        articles = [
            NewsArticle(
                title="Test Article",
                summary="This is a test summary",
                source="BBC",
                url="https://example.com/test",
                published=datetime(2024, 1, 1, 12, 0),
                category="technology",
            ),
        ]
        result = format_news_for_agent(articles)
        assert "Test Article" in result
        assert "BBC" in result
        assert "technology" in result


class TestFunTools:
    """Tests for fun segment tools."""

    def test_quote_has_required_fields(self):
        """Test Quote dataclass has required fields."""
        quote = Quote(text="Test quote", author="Test Author")
        assert quote.text == "Test quote"
        assert quote.author == "Test Author"

    def test_dad_joke_has_required_fields(self):
        """Test DadJoke dataclass has required fields."""
        joke = DadJoke(setup="Why did the chicken cross the road?", punchline="To get to the other side!")
        assert joke.setup == "Why did the chicken cross the road?"
        assert joke.punchline == "To get to the other side!"

    def test_format_fun_content_empty(self):
        """Test formatting with empty content."""
        result = format_fun_content_for_agent({})
        # Should only have the header
        assert "# Fun Segments" in result

    def test_format_fun_content_with_quote(self):
        """Test formatting with a quote."""
        content = {
            "quote_of_the_day": Quote(
                text="The only way to do great work is to love what you do.",
                author="Steve Jobs"
            )
        }
        result = format_fun_content_for_agent(content)
        assert "Quote of the Day" in result
        assert "Steve Jobs" in result


class TestMusicTools:
    """Tests for music tools."""

    def test_music_piece_info_creation(self):
        """Test MusicPieceInfo creation."""
        piece = MusicPieceInfo(
            id=1,
            composer="Johann Sebastian Bach",
            title="Air on the G String",
            description="A beautiful piece",
            duration_seconds=300.0,
            s3_key="music/bach/air_on_g_string.mp3",
        )
        assert piece.id == 1
        assert piece.composer == "Johann Sebastian Bach"
        assert piece.title == "Air on the G String"
        assert piece.duration_seconds == 300.0

    def test_format_music_for_agent(self):
        """Test formatting music piece for agent."""
        piece = MusicPieceInfo(
            id=1,
            composer="Johann Sebastian Bach",
            title="Air on the G String",
            description="A beautiful baroque piece from the Orchestral Suite No. 3",
            duration_seconds=300.0,
            s3_key="music/bach/air_on_g_string.mp3",
        )
        result = format_music_for_agent(piece)
        assert "Johann Sebastian Bach" in result
        assert "Air on the G String" in result
        assert "MUSIC SEGMENT" in result
        assert "WILL play" in result

    def test_format_music_for_agent_without_description(self):
        """Test formatting music piece without description."""
        piece = MusicPieceInfo(
            id=1,
            composer="Erik Satie",
            title="Gymnopédie No. 1",
            description=None,
            duration_seconds=180.0,
            s3_key="music/satie/gymnopedie_no1.mp3",
        )
        result = format_music_for_agent(piece)
        assert "Erik Satie" in result
        assert "Gymnopédie No. 1" in result
        assert "warm and welcoming" in result


class TestHistoricalEvent:
    """Tests for historical event dataclass."""

    def test_historical_event_creation(self):
        """Test HistoricalEvent creation."""
        event = HistoricalEvent(
            year=1969,
            description="Apollo 11 lands on the moon",
            category="event",
        )
        assert event.year == 1969
        assert "Apollo" in event.description
        assert event.category == "event"
