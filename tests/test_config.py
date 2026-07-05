"""Tests for the Settings backbone."""
from __future__ import annotations

from scrumbot.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    # NVIDIA NIM / Nemotron is the core-brain agent model.
    assert settings.scrum_agent_model == "nvidia/llama-3.1-nemotron-70b-instruct"
    # Gemini is the "second brain" for quick single-shot generations.
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.embedding_provider == "fastembed"
    assert settings.queue_workers == 3
    assert settings.mcp_transport == "stdio"


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SCRUM_AGENT_MODEL", "gpt-4o")
    monkeypatch.setenv("QUEUE_WORKERS", "7")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    settings = Settings(_env_file=None)
    assert settings.scrum_agent_model == "gpt-4o"
    assert settings.queue_workers == 7
    assert settings.embedding_provider == "openai"
