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

    openrouter_api_key: str = ""     
    google_api_key: str = ""        
    openai_api_key: str = ""          
    anthropic_api_key: str = ""       
    groq_api_key: str = ""             
    devin_default_model: str = "gemini-2.0-flash"
    devin_architect_model: str = ""   
    devin_worker_model: str = ""      
    devin_companion_model: str = ""   
    devin_fallback_models: str = "gemini-2.5-flash"

    tavily_api_key: str = ""           

    def get_architect_model(self) -> str:
        return self.devin_architect_model or self.devin_default_model
    
    def get_worker_model(self) -> str:
        return self.devin_worker_model or self.devin_default_model
    
    def get_companion_model(self) -> str:
        return self.devin_companion_model or self.devin_default_model
    
    def get_fallback_chain(self) -> list[str]:
        return [m.strip() for m in self.devin_fallback_models.split(",") if m.strip()]

    langsmith_api_key: str = ""
    langsmith_project: str = "devin"
    langsmith_tracing: bool = False

    devin_max_iterations: int = 15
    devin_require_confirmation: bool = True

    chroma_persist_dir: str = "./data/chromadb"

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

    def has_groq(self) -> bool:
        return bool(
            self.groq_api_key
            and self.groq_api_key != "gsk_your-groq-key-here"
        )

    def get_available_provider(self) -> str:
        """Return the best available LLM provider. Prefers free (Google) first."""
        model = self.devin_default_model.lower()

        if "gemini" in model and self.has_google():
            return "google"
        if "gpt-" in model or "o1-" in model or "o3-" in model or "o4-" in model:
            if self.has_openai():
                return "openai"
        if "claude" in model and self.has_anthropic():
            return "anthropic"
        if ("llama" in model or "mixtral" in model or "gemma" in model) and self.has_groq():
            return "groq"

        if self.has_google():
            return "google"
        if self.has_groq():
            return "groq"
        if self.has_openai():
            return "openai"
        if self.has_anthropic():
            return "anthropic"

        raise ValueError(
            "No LLM provider configured. Set GOOGLE_API_KEY or GROQ_API_KEY in .env"
        )


settings = DevinSettings()
