"""Centralised configuration and logging.

A single :class:`Settings` object is the source of truth for every
environment-driven value in the application. Modules must never call
``os.environ`` directly -- they read from ``get_settings()`` instead, which
makes the wiring explicit and the code trivially testable (inject a ``Settings``
built with overrides).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment / ``.env``.

    Field names map to upper-cased environment variables automatically
    (``scrum_agent_model`` <- ``SCRUM_AGENT_MODEL``), so no manual aliasing is
    required.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM ---------------------------------------------------------------
    scrum_agent_model: str = "gemini-2.5-flash"
    scrum_agent_temperature: float = 0.0
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    # Gemini is the "second brain": quick single-shot generations (blocker
    # advice, standup nudges) via the google-genai SDK, separate from the
    # NVIDIA NIM / Nemotron core agent used by the slash commands.
    gemini_model: str = "gemini-2.5-flash"
    nvidia_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"

    # --- Discord -----------------------------------------------------------
    discord_token: Optional[str] = None
    scrum_bot_token: Optional[str] = None
    discord_client_id: Optional[str] = None
    discord_client_secret: Optional[str] = None
    # Channel the scheduled daily standup is posted to; unset disables it.
    standup_channel_id: Optional[int] = None
    # Channel for autonomous background reports.
    autonomous_channel_id: Optional[int] = None
    autonomous_interval_minutes: int = 5

    # --- DevOps backend ----------------------------------------------------
    devops_api_url: str = "http://localhost:8000/api"
    bot_api_key: str = ""
    devops_timeout_seconds: float = 15.0
    devops_max_retries: int = 3
    devops_max_connections: int = 20

    # --- Vector store / embeddings ----------------------------------------
    chroma_db_path: str = "resources/chroma"
    chroma_collection: str = "discord_chat_data"
    # "fastembed" runs a local ONNX model (no API key, no network); "openai"
    # uses the hosted embedding endpoint. Local is the default so semantic
    # search is genuinely in-process, matching the performance claims.
    embedding_provider: Literal["fastembed", "openai"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # --- Agent memory / checkpointer --------------------------------------
    # If set, LangGraph state is persisted to PostgreSQL; otherwise an in-process
    # MemorySaver is used (conversation memory survives within a process).
    database_url: Optional[str] = None

    # --- Async work queue --------------------------------------------------
    queue_workers: int = 3

    # --- MCP server --------------------------------------------------------
    mcp_transport: Literal["stdio", "http", "sse"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    # --- Integrations ------------------------------------------------------
    composio_api_key: Optional[str] = None
    # Composio is opt-in. Tools only load when an API key AND a user id with
    # connected accounts are configured; ``composio_toolkits`` is a
    # comma-separated allowlist (e.g. "GMAIL,GITHUB"). Empty => no Composio tools.
    composio_user_id: Optional[str] = None
    composio_toolkits: Optional[str] = None
    whatsapp_verify_token: Optional[str] = "launchpixel_token"

    # --- Webhook receiver (DevOps -> Discord) ------------------------------
    # When webhook_secret is set, `--mode both` also starts the receiver.
    webhook_secret: Optional[str] = None
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    # Channel that inbound board events are announced in.
    notify_channel_id: Optional[int] = None

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once and cached."""
    return Settings()


def setup_logging(level: Optional[str] = None) -> None:
    """Configure root logging once, idempotently.

    Args:
        level: Overrides ``Settings.log_level`` when provided.
    """
    resolved = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=getattr(logging, resolved, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Silence noisy third-party loggers unless we're explicitly debugging.
    if resolved != "DEBUG":
        for noisy in ("httpx", "httpcore", "discord", "chromadb"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
