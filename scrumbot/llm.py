"""LLM factory.

Resolves a model name to a configured LangChain chat model. Provider routing is
prefix/namespace based so it is unambiguous:

* ``ollama/<model>``            -> local Ollama            (e.g. ``ollama/llama3``)
* ``gemini-*``                  -> Google Generative AI    (e.g. ``gemini-1.5-pro``)
* ``claude-*``                  -> Anthropic               (e.g. ``claude-3-5-sonnet-latest``)
* ``gpt-*`` / ``*openai*``      -> OpenAI                  (e.g. ``gpt-4o``)
* ``<vendor>/<model>``          -> NVIDIA NIM (OpenAI API) (e.g. ``meta/llama-3.1-70b-instruct``)

Keys and temperature are injected from :class:`~scrumbot.config.Settings` rather
than read from ambient environment, which keeps the factory testable.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel

from scrumbot.config import Settings, get_settings


def _maybe(name: str, value: Optional[str]) -> Dict[str, Any]:
    """Include ``{name: value}`` only when ``value`` is set.

    Passing an explicit ``None`` would stop LangChain falling back to its own
    environment lookup, so we omit the key entirely when we have no override.
    """
    return {name: value} if value else {}


def get_llm(
    model_name: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> BaseChatModel:
    """Build a chat model for ``model_name`` (defaults to the configured model)."""
    settings = settings or get_settings()
    model = model_name or settings.scrum_agent_model
    temperature = settings.scrum_agent_temperature
    lowered = model.lower()

    if lowered.startswith("ollama/"):
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model.split("/", 1)[1],
            temperature=temperature,
            base_url=settings.ollama_base_url,
        )

    if "gemini" in lowered:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            **_maybe("google_api_key", settings.google_api_key),
        )

    if "claude" in lowered:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            **_maybe("api_key", settings.anthropic_api_key),
        )

    if "gpt" in lowered or "openai" in lowered:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            **_maybe("api_key", settings.openai_api_key),
        )

    if "/" in model:  # vendor-namespaced NVIDIA NIM catalogue entry
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url="https://integrate.api.nvidia.com/v1",
            **_maybe("api_key", settings.nvidia_api_key),
        )

    raise ValueError(
        f"Unsupported model: {model!r}. Prefix Ollama models with 'ollama/' and "
        "NVIDIA NIM models with a vendor namespace (e.g. 'meta/llama-3.1-70b-instruct')."
    )
