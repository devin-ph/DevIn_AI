"""Tests for DevIn settings."""

import os

from devin.settings import DevinSettings


class TestSettings:
    """Tests for the settings module."""

    def test_default_values(self):
        # Must pass env_file=None to ignore local .env file in tests
        settings = DevinSettings(
            _env_file=None,
            google_api_key="",
            openai_api_key="",
            anthropic_api_key="",
        )
        assert settings.devin_default_model == "gemini-2.0-flash"
        assert settings.devin_max_iterations == 15
        assert settings.devin_require_confirmation is True

    def test_has_google_false_with_placeholder(self):
        settings = DevinSettings(_env_file=None, google_api_key="your-gemini-api-key-here")
        assert settings.has_google() is False

    def test_has_google_true_with_real_key(self):
        settings = DevinSettings(_env_file=None, google_api_key="AIzaSyA-12345realkey")
        assert settings.has_google() is True

    def test_provider_detection_google(self):
        settings = DevinSettings(
            _env_file=None,
            google_api_key="AIzaSyA-real",
            devin_default_model="gemini-2.0-flash",
        )
        assert settings.get_available_provider() == "google"

    def test_provider_detection_openai_fallback(self):
        settings = DevinSettings(
            _env_file=None,
            google_api_key="",
            openai_api_key="sk-real",
            devin_default_model="gpt-4o",
        )
        assert settings.get_available_provider() == "openai"

    def test_no_provider_raises(self):
        settings = DevinSettings(_env_file=None, google_api_key="", openai_api_key="", anthropic_api_key="")
        try:
            settings.get_available_provider()
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
