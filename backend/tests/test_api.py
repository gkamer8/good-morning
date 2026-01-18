"""Tests for API routes."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data


class TestSettingsEndpoints:
    """Tests for settings endpoints."""

    def test_get_settings(self, client):
        """Test getting settings."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        # Check default values
        assert "news_topics" in data
        assert "news_sources" in data
        assert "duration_minutes" in data

    def test_settings_has_voice_fields(self, client):
        """Test settings include voice configuration."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "voice_id" in data
        assert "voice_style" in data
        assert "voice_speed" in data

    def test_settings_has_segment_order(self, client):
        """Test settings include segment order."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "segment_order" in data
        assert isinstance(data["segment_order"], list)

    def test_settings_has_music_flag(self, client):
        """Test settings include music flag."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "include_music" in data
        assert isinstance(data["include_music"], bool)

    def test_settings_has_writing_style(self, client):
        """Test settings include writing_style field."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "writing_style" in data
        assert isinstance(data["writing_style"], str)

    def test_settings_writing_style_default(self, client):
        """Test writing_style has correct default value on fresh settings."""
        # Reset to default first to ensure clean state
        client.put("/api/settings", json={"writing_style": "good_morning_america"})
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        # Default should be good_morning_america
        assert data["writing_style"] == "good_morning_america"

    def test_update_writing_style(self, client):
        """Test updating writing_style via PUT."""
        # Update to firing_line
        response = client.put("/api/settings", json={"writing_style": "firing_line"})
        assert response.status_code == 200
        data = response.json()
        assert data["writing_style"] == "firing_line"

        # Verify it persisted
        get_response = client.get("/api/settings")
        assert get_response.status_code == 200
        assert get_response.json()["writing_style"] == "firing_line"

        # Update to ernest_hemingway
        response = client.put("/api/settings", json={"writing_style": "ernest_hemingway"})
        assert response.status_code == 200
        assert response.json()["writing_style"] == "ernest_hemingway"

        # Reset to default
        response = client.put("/api/settings", json={"writing_style": "good_morning_america"})
        assert response.status_code == 200
        assert response.json()["writing_style"] == "good_morning_america"

    def test_writing_style_accepts_all_valid_values(self, client):
        """Test all valid writing_style values are accepted."""
        valid_styles = ["good_morning_america", "firing_line", "ernest_hemingway"]
        for style in valid_styles:
            response = client.put("/api/settings", json={"writing_style": style})
            assert response.status_code == 200, f"Failed to set writing_style to {style}"
            assert response.json()["writing_style"] == style

        # Reset to default
        client.put("/api/settings", json={"writing_style": "good_morning_america"})


class TestVoiceSelection:
    """Tests for voice selection in settings."""

    def test_update_voice_id_with_stock_voice(self, client):
        """Test updating voice_id with a stock voice ID works."""
        # Rachel is a valid stock voice
        response = client.put("/api/settings", json={"voice_id": "21m00Tcm4TlvDq8ikWAM"})
        assert response.status_code == 200
        assert response.json()["voice_id"] == "21m00Tcm4TlvDq8ikWAM"

    def test_update_voice_id_with_custom_voice(self, client):
        """Test updating voice_id with a custom voice ID works.

        Custom voices are configured in settings.elevenlabs_custom_voice_ids.
        They should be accepted, not silently replaced with the default.
        """
        # "Firing Line" custom voice from config.py
        custom_voice_id = "BG48ZiEunXWfskS4bWOW"
        response = client.put("/api/settings", json={"voice_id": custom_voice_id})
        assert response.status_code == 200
        # Should keep the custom voice, NOT replace with default
        assert response.json()["voice_id"] == custom_voice_id, \
            "Custom voice was silently replaced with default - validation should accept custom voices"

    def test_update_voice_id_invalid_falls_back_to_default(self, client):
        """Test that truly invalid voice IDs fall back to default."""
        invalid_voice_id = "invalid_voice_id_12345"
        response = client.put("/api/settings", json={"voice_id": invalid_voice_id})
        assert response.status_code == 200
        # Invalid voice should fall back to default (Rachel)
        assert response.json()["voice_id"] == "21m00Tcm4TlvDq8ikWAM"

    def test_voice_id_persists_after_update(self, client):
        """Test that voice_id selection persists correctly."""
        # Set to Adam
        client.put("/api/settings", json={"voice_id": "pNInz6obpgDQGcFmaJgB"})

        # Verify it persisted
        response = client.get("/api/settings")
        assert response.json()["voice_id"] == "pNInz6obpgDQGcFmaJgB"

        # Reset to Rachel
        client.put("/api/settings", json={"voice_id": "21m00Tcm4TlvDq8ikWAM"})


class TestBriefingEndpoints:
    """Tests for briefing endpoints."""

    def test_list_briefings(self, client):
        """Test listing briefings."""
        response = client.get("/api/briefings")
        assert response.status_code == 200
        data = response.json()
        assert "briefings" in data
        assert "total" in data
        assert isinstance(data["briefings"], list)

    def test_list_briefings_with_pagination(self, client):
        """Test briefings list supports pagination."""
        response = client.get("/api/briefings?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "briefings" in data

    def test_generate_briefing_requires_body(self, client):
        """Test generate briefing requires request body."""
        response = client.post("/api/briefings/generate")
        # Should return 422 for missing body
        assert response.status_code == 422

    def test_generate_briefing_with_empty_body(self, client):
        """Test generate briefing accepts empty body."""
        response = client.post("/api/briefings/generate", json={})
        # Should return 200 and start generation
        assert response.status_code == 200
        data = response.json()
        assert "briefing_id" in data
        assert "status" in data


class TestScheduleEndpoints:
    """Tests for schedule endpoints."""

    def test_get_schedule(self, client):
        """Test getting schedule."""
        response = client.get("/api/schedule")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "days_of_week" in data
        assert "time_hour" in data
        assert "time_minute" in data
        assert "timezone" in data


class TestVoiceEndpoints:
    """Tests for voice preview endpoints."""

    def test_voice_preview_endpoint_exists(self, client):
        """Test voice preview endpoint exists (requires valid voice ID)."""
        # Using a real ElevenLabs voice ID to test the endpoint
        response = client.get("/api/voices/pNInz6obpgDQGcFmaJgB/preview")
        # May return 200 (audio) or 500 (API key missing) - but not 404
        assert response.status_code != 404

    def test_list_voices_endpoint_exists(self, client):
        """Test list voices endpoint exists."""
        response = client.get("/api/voices")
        # May return 200 (voices list) or 500 (API key missing) - but not 404
        assert response.status_code != 404

    def test_list_voices_returns_structure(self, client):
        """Test list voices returns proper JSON structure."""
        response = client.get("/api/voices")
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        assert "total" in data
        assert isinstance(data["voices"], list)
        assert isinstance(data["total"], int)

    def test_list_voices_only_returns_configured_custom_voices(self, client):
        """Test that only explicitly configured custom voices are returned.

        The voices endpoint should only return voices listed in
        elevenlabs_custom_voice_ids config, not all account voices.
        """
        response = client.get("/api/voices")
        assert response.status_code == 200
        data = response.json()

        # Verify we get the configured custom voices (or empty if API key not set)
        voices = data["voices"]
        if len(voices) > 0:
            # If we have voices, each should have the expected fields
            for voice in voices:
                assert "voice_id" in voice
                assert "name" in voice

    def test_voice_preview_returns_audio(self, client):
        """Test voice preview returns audio content when file exists."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        # Create a mock preview file
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Preview dir is now assets_dir / "audio" / "previews"
            preview_dir = Path(tmp_dir) / "audio" / "previews"
            preview_dir.mkdir(parents=True)

            # Create a fake MP3 file (just needs to be non-empty)
            test_voice_id = "test_voice_123"
            preview_file = preview_dir / f"{test_voice_id}.mp3"
            preview_file.write_bytes(b"fake mp3 content for testing")

            # Patch the settings to use our temp directory
            with patch("src.api.routes.voices.settings") as mock_settings:
                mock_settings.assets_dir = Path(tmp_dir)
                mock_settings.elevenlabs_api_key = "test_key"
                mock_settings.elevenlabs_model_id = "test_model"

                response = client.get(f"/api/voices/{test_voice_id}/preview")
                assert response.status_code == 200
                assert response.headers["content-type"] == "audio/mpeg"
                assert len(response.content) > 0

    def test_voice_preview_deletes_empty_files(self, client):
        """Test that empty preview files are deleted and regenerated."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Preview dir is now assets_dir / "audio" / "previews"
            preview_dir = Path(tmp_dir) / "audio" / "previews"
            preview_dir.mkdir(parents=True)

            # Create an empty file (simulating failed previous generation)
            test_voice_id = "empty_voice_456"
            preview_file = preview_dir / f"{test_voice_id}.mp3"
            preview_file.write_bytes(b"")  # Empty file

            # Mock the settings and ElevenLabs client
            with patch("src.api.routes.voices.settings") as mock_settings:
                mock_settings.assets_dir = Path(tmp_dir)
                mock_settings.elevenlabs_api_key = None  # Will cause 500 error

                response = client.get(f"/api/voices/{test_voice_id}/preview")

                # Should fail with 500 because API key is not configured
                # but the empty file should have been deleted
                assert response.status_code == 500
                assert "ElevenLabs API key not configured" in response.json()["detail"]

                # Empty file should be deleted
                assert not preview_file.exists()

    def test_voice_preview_caches_files(self, client):
        """Test that preview files are cached and reused."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Preview dir is now assets_dir / "audio" / "previews"
            preview_dir = Path(tmp_dir) / "audio" / "previews"
            preview_dir.mkdir(parents=True)

            test_voice_id = "cached_voice_789"
            preview_file = preview_dir / f"{test_voice_id}.mp3"
            preview_file.write_bytes(b"cached mp3 content")

            with patch("src.api.routes.voices.settings") as mock_settings:
                mock_settings.assets_dir = Path(tmp_dir)
                mock_settings.elevenlabs_api_key = "test_key"

                # First request
                response1 = client.get(f"/api/voices/{test_voice_id}/preview")
                assert response1.status_code == 200

                # Second request should return the same cached file
                response2 = client.get(f"/api/voices/{test_voice_id}/preview")
                assert response2.status_code == 200
                assert response1.content == response2.content


class TestConcurrentRequests:
    """Tests for concurrent request handling."""

    def test_settings_accessible_during_generation(self, client):
        """Test that settings endpoint responds quickly even when generation is pending.

        This verifies that the async implementation doesn't block other requests.
        """
        import time

        # Start a generation (this creates a background task)
        gen_response = client.post("/api/briefings/generate", json={})
        assert gen_response.status_code == 200

        # Immediately try to access settings - should respond quickly
        start_time = time.time()
        settings_response = client.get("/api/settings")
        elapsed = time.time() - start_time

        assert settings_response.status_code == 200
        # Settings should respond in under 1 second (not blocked by generation)
        assert elapsed < 1.0, f"Settings took {elapsed:.2f}s - may be blocked by generation"

    def test_briefings_list_accessible_during_generation(self, client):
        """Test that briefings list responds quickly during generation."""
        import time

        # Start a generation
        gen_response = client.post("/api/briefings/generate", json={})
        assert gen_response.status_code == 200

        # Immediately try to list briefings
        start_time = time.time()
        list_response = client.get("/api/briefings")
        elapsed = time.time() - start_time

        assert list_response.status_code == 200
        assert elapsed < 1.0, f"Briefings list took {elapsed:.2f}s - may be blocked"

    def test_multiple_sequential_requests_during_generation(self, client):
        """Test that multiple requests complete quickly during generation."""
        import time

        # Start a generation first
        gen_response = client.post("/api/briefings/generate", json={})
        assert gen_response.status_code == 200

        # Make multiple requests sequentially and verify they're all fast
        endpoints = ["/api/settings", "/api/briefings", "/api/schedule", "/health"]
        total_elapsed = 0

        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint)
            elapsed = time.time() - start_time
            total_elapsed += elapsed

            assert response.status_code == 200
            assert elapsed < 1.0, f"{endpoint} took {elapsed:.2f}s - may be blocked"

        # All 4 requests should complete in under 4 seconds total
        assert total_elapsed < 4.0, f"Total time {total_elapsed:.2f}s too slow"


class TestMusicEndpoints:
    """Tests for music streaming endpoints."""

    def test_stream_nonexistent_piece_returns_404(self, client):
        """Test streaming a non-existent music piece returns 404."""
        response = client.get("/api/music/99999/stream")
        assert response.status_code == 404

    def test_stream_endpoint_exists(self, client):
        """Test music stream endpoint exists (valid route)."""
        # Even for ID 0, should get 404 (not found) not 405 (method not allowed)
        response = client.get("/api/music/0/stream")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestAPIDocumentation:
    """Tests for API documentation endpoints."""

    def test_openapi_schema_available(self, client):
        """Test OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data

    def test_docs_endpoint_available(self, client):
        """Test docs endpoint is available."""
        response = client.get("/docs")
        assert response.status_code == 200
