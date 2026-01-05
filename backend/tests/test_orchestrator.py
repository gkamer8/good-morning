"""Tests for the orchestrator writing style feature."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.agents.orchestrator import (
    WRITING_STYLES,
    DEFAULT_WRITING_STYLE,
    SCRIPT_WRITER_SYSTEM_PROMPT_TEMPLATE,
    generate_script_with_claude,
)


class TestWritingStylesConfiguration:
    """Tests for writing styles configuration."""

    def test_writing_styles_contains_required_styles(self):
        """Test all required writing styles are defined."""
        required_styles = ["good_morning_america", "firing_line", "ernest_hemingway"]
        for style in required_styles:
            assert style in WRITING_STYLES, f"Missing required style: {style}"

    def test_each_style_has_name_and_prompt(self):
        """Test each writing style has required fields."""
        for style_id, style_config in WRITING_STYLES.items():
            assert "name" in style_config, f"Style {style_id} missing 'name'"
            assert "prompt" in style_config, f"Style {style_id} missing 'prompt'"
            assert len(style_config["name"]) > 0, f"Style {style_id} has empty name"
            assert len(style_config["prompt"]) > 0, f"Style {style_id} has empty prompt"

    def test_default_writing_style_exists(self):
        """Test default writing style is defined and valid."""
        assert DEFAULT_WRITING_STYLE is not None
        assert DEFAULT_WRITING_STYLE in WRITING_STYLES

    def test_good_morning_america_style(self):
        """Test Good Morning America style has appropriate content."""
        style = WRITING_STYLES["good_morning_america"]
        assert style["name"] == "Good Morning, America"
        # Should mention upbeat/energetic
        prompt_lower = style["prompt"].lower()
        assert "upbeat" in prompt_lower or "energetic" in prompt_lower

    def test_firing_line_style(self):
        """Test Firing Line style has appropriate content."""
        style = WRITING_STYLES["firing_line"]
        assert style["name"] == "Firing Line"
        # Should mention William F. Buckley or intellectual/wit
        prompt_lower = style["prompt"].lower()
        assert "buckley" in prompt_lower or "intellectual" in prompt_lower or "wit" in prompt_lower

    def test_ernest_hemingway_style(self):
        """Test Ernest Hemingway style has appropriate content."""
        style = WRITING_STYLES["ernest_hemingway"]
        assert style["name"] == "Ernest Hemingway"
        # Should mention short/direct/terse
        prompt_lower = style["prompt"].lower()
        assert "short" in prompt_lower or "direct" in prompt_lower or "terse" in prompt_lower


class TestSystemPromptTemplate:
    """Tests for the system prompt template."""

    def test_template_has_writing_style_placeholder(self):
        """Test system prompt template includes writing style placeholder."""
        assert "{writing_style_instructions}" in SCRIPT_WRITER_SYSTEM_PROMPT_TEMPLATE

    def test_template_can_be_formatted_with_all_placeholders(self):
        """Test template accepts all required placeholders."""
        # This should not raise an exception
        formatted = SCRIPT_WRITER_SYSTEM_PROMPT_TEMPLATE.format(
            segment_flow="News -> Sports -> Weather",
            classical_music_instruction="",
            writing_style_instructions="Test style instructions",
        )
        assert "Test style instructions" in formatted
        assert "News -> Sports -> Weather" in formatted


class TestGenerateScriptWithClaude:
    """Tests for generate_script_with_claude function with writing styles."""

    @pytest.fixture
    def mock_content(self):
        """Sample content for testing."""
        return {
            "news": "Test news content",
            "sports": "Test sports content",
            "weather": "Test weather content",
            "fun": "Test fun content",
            "market": "",
            "music": "",
        }

    @pytest.mark.asyncio
    async def test_generate_script_uses_default_style_when_none(self, mock_content):
        """Test that default style is used when no style specified."""
        with patch("src.agents.orchestrator.AsyncAnthropic") as mock_anthropic:
            # Setup mock
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            mock_message = MagicMock()
            mock_message.content = [MagicMock(text='{"segments": []}')]
            mock_client.messages.create = AsyncMock(return_value=mock_message)

            with patch("src.agents.orchestrator.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = "test-key"

                await generate_script_with_claude(
                    mock_content,
                    target_duration_minutes=10,
                    writing_style=None,  # No style specified
                )

                # Verify the call was made with the default style in the system prompt
                call_args = mock_client.messages.create.call_args
                system_prompt = call_args.kwargs["system"]

                # Should contain the default style's prompt content
                default_style_prompt = WRITING_STYLES[DEFAULT_WRITING_STYLE]["prompt"]
                assert any(word in system_prompt for word in default_style_prompt.split()[:5])

    @pytest.mark.asyncio
    async def test_generate_script_uses_specified_style(self, mock_content):
        """Test that specified writing style is used in prompt."""
        with patch("src.agents.orchestrator.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            mock_message = MagicMock()
            mock_message.content = [MagicMock(text='{"segments": []}')]
            mock_client.messages.create = AsyncMock(return_value=mock_message)

            with patch("src.agents.orchestrator.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = "test-key"

                await generate_script_with_claude(
                    mock_content,
                    target_duration_minutes=10,
                    writing_style="firing_line",
                )

                call_args = mock_client.messages.create.call_args
                system_prompt = call_args.kwargs["system"]

                # Should contain Firing Line style content
                assert "Buckley" in system_prompt or "intellectual" in system_prompt.lower()

    @pytest.mark.asyncio
    async def test_generate_script_hemingway_style(self, mock_content):
        """Test Hemingway style is properly injected."""
        with patch("src.agents.orchestrator.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            mock_message = MagicMock()
            mock_message.content = [MagicMock(text='{"segments": []}')]
            mock_client.messages.create = AsyncMock(return_value=mock_message)

            with patch("src.agents.orchestrator.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = "test-key"

                await generate_script_with_claude(
                    mock_content,
                    target_duration_minutes=10,
                    writing_style="ernest_hemingway",
                )

                call_args = mock_client.messages.create.call_args
                system_prompt = call_args.kwargs["system"]

                # Should contain Hemingway style content
                hemingway_prompt = WRITING_STYLES["ernest_hemingway"]["prompt"]
                # Check for key Hemingway style words
                assert "short" in system_prompt.lower() or "direct" in system_prompt.lower()

    @pytest.mark.asyncio
    async def test_generate_script_falls_back_to_default_for_invalid_style(self, mock_content):
        """Test that invalid style falls back to default."""
        with patch("src.agents.orchestrator.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            mock_message = MagicMock()
            mock_message.content = [MagicMock(text='{"segments": []}')]
            mock_client.messages.create = AsyncMock(return_value=mock_message)

            with patch("src.agents.orchestrator.get_settings") as mock_settings:
                mock_settings.return_value.anthropic_api_key = "test-key"

                # Use an invalid style
                await generate_script_with_claude(
                    mock_content,
                    target_duration_minutes=10,
                    writing_style="invalid_style_that_doesnt_exist",
                )

                call_args = mock_client.messages.create.call_args
                system_prompt = call_args.kwargs["system"]

                # Should fall back to default style
                default_style_prompt = WRITING_STYLES[DEFAULT_WRITING_STYLE]["prompt"]
                # Check that the default style prompt content is used
                assert "upbeat" in system_prompt.lower() or "energetic" in system_prompt.lower()
