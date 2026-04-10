"""
DevIn Settings — Centralized configuration management.

Uses pydantic-settings to load from .env file with type validation.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class DevinSettings(BaseSettings):
    """Global settings for DevIn, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    # --- LLM Providers ---
    openrouter_api_key: str = ""       # Default OpenRouter gateway
    google_api_key: str = ""           # FREE — Google Gemini
    openai_api_key: str = ""           # Optional (paid)
    anthropic_api_key: str = ""        # Optional (paid)
    devin_default_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    # --- Search ---
    tavily_api_key: str = ""           # Optional — DuckDuckGo is the free default

    # --- Observability ---
    langsmith_api_key: str = ""
    langsmith_project: str = "devin"
    langsmith_tracing: bool = False

    # --- Safety ---
    devin_max_iterations: int = 15
    devin_require_confirmation: bool = True

    # --- Memory ---
    chroma_persist_dir: str = "./data/chromadb"

    # --- Paths ---
    workspace_dir: str = "."

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_dir).resolve()

    def has_google(self) -> bool:
        return bool(
            self.google_api_key
            and self.google_api_key != "your-gemini-api-key-here"
        )

    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key != "sk-your-openai-key-here")

    def has_anthropic(self) -> bool:
        return bool(
            self.anthropic_api_key
            and self.anthropic_api_key != "sk-ant-your-anthropic-key-here"
        )

    def get_available_provider(self) -> str:
        """Return the best available LLM provider. Prefers free (Google) first."""
        model = self.devin_default_model.lower()

        # If model name explicitly indicates a provider, use that
        if "gemini" in model and self.has_google():
            return "google"
        if "gpt-" in model or "o1-" in model or "o3-" in model or "o4-" in model:
            if self.has_openai():
                return "openai"
        if "claude" in model and self.has_anthropic():
            return "anthropic"

        # Auto-detect: prefer free providers first
        if self.has_google():
            return "google"
        if self.has_openai():
            return "openai"
        if self.has_anthropic():
            return "anthropic"

        raise ValueError(
            "No LLM provider configured. Set GOOGLE_API_KEY in .env\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )


# Global singleton
settings = DevinSettings()
