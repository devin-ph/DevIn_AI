"""
DevIn LLM Provider — Abstraction layer for LLM backends.

This module provides a unified interface to create LLM instances.
Supports Google Gemini (FREE), OpenAI, Anthropic, with Ollama (local) for Phase 5.
The abstraction ensures we can swap providers without touching agent logic.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel

from devin.settings import settings

logger = logging.getLogger(__name__)


def create_llm(
    model: str | None = None,
    temperature: float = 0.1,
    streaming: bool = True,
    **kwargs,
) -> BaseChatModel:
    model = model or settings.devin_default_model

    # Use OpenRouter if OPENROUTER_API_KEY exists and the model isn't strictly OpenAI/Anthropic/Google specific
    # Or just fallback to the specific logic
    if getattr(settings, "openrouter_api_key", None):
        return _create_openrouter(model, temperature, streaming, **kwargs)
        
    if _is_google_model(model):
        return _create_google(model, temperature, streaming, **kwargs)
    elif _is_openai_model(model):
        return _create_openai(model, temperature, streaming, **kwargs)
    elif _is_anthropic_model(model):
        return _create_anthropic(model, temperature, streaming, **kwargs)
    else:
        provider = settings.get_available_provider()
        if provider == "google":
            return _create_google(model, temperature, streaming, **kwargs)
        elif provider == "openai":
            return _create_openai(model, temperature, streaming, **kwargs)
        else:
            return _create_anthropic(model, temperature, streaming, **kwargs)


def _is_google_model(model: str) -> bool:
    return model.startswith("gemini")


def _is_openai_model(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in ["gpt-", "o1-", "o3-", "o4-"])


def _is_anthropic_model(model: str) -> bool:
    return model.startswith("claude-")

def _create_openrouter(
    model: str, temperature: float, streaming: bool, **kwargs
) -> BaseChatModel:
    """Create an OpenRouter chat model using LangChain OpenAI adapter."""
    from langchain_openai import ChatOpenAI

    logger.info(f"Creating OpenRouter LLM: {model}")
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=4000,
        streaming=streaming,
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
        **kwargs,
    )


def _create_google(
    model: str, temperature: float, streaming: bool, **kwargs
) -> BaseChatModel:
    """Create a Google Gemini chat model (FREE tier)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.has_google():
        raise ValueError(
            "Google API key not configured. Set GOOGLE_API_KEY in .env\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )

    logger.info(f"Creating Google Gemini LLM: {model} (FREE)")
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=settings.google_api_key,
        convert_system_message_to_human=False,
        **kwargs,
    )


def _create_openai(
    model: str, temperature: float, streaming: bool, **kwargs
) -> BaseChatModel:
    """Create an OpenAI chat model."""
    from langchain_openai import ChatOpenAI

    if not settings.has_openai():
        raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env")

    logger.info(f"Creating OpenAI LLM: {model}")
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        streaming=streaming,
        api_key=settings.openai_api_key,
        **kwargs,
    )


def _create_anthropic(
    model: str, temperature: float, streaming: bool, **kwargs
) -> BaseChatModel:
    """Create an Anthropic chat model."""
    from langchain_anthropic import ChatAnthropic

    if not settings.has_anthropic():
        raise ValueError("Anthropic API key not configured. Set ANTHROPIC_API_KEY in .env")

    logger.info(f"Creating Anthropic LLM: {model}")
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        streaming=streaming,
        api_key=settings.anthropic_api_key,
        **kwargs,
    )
