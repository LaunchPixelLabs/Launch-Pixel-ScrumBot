"""Async HTTP client for the DevOps backend.

A single pooled :class:`httpx.AsyncClient` is created per :class:`DevOpsClient`
and reused across every request, so keep-alive connections are actually reused
(the old implementation opened and tore down a client on every call). Transient
failures are retried with exponential backoff; the lifecycle is explicit via
``aclose`` / async-context-manager so the owning application can shut it down
cleanly.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scrumbot.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Status codes worth retrying: rate limiting + transient server errors.
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class _RetryableStatusError(Exception):
    """Raised internally to trigger a retry on a transient HTTP status."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"retryable status {response.status_code}")
        self.response = response


class DevOpsClient:
    """Thin async wrapper over the DevOps REST API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._settings = settings or get_settings()
        # When a client is injected (e.g. in tests) we don't own its lifecycle.
        self._owns_client = client is None
        self._client = client or self._build_client(self._settings)

    @staticmethod
    def _build_client(settings: Settings) -> httpx.AsyncClient:
        max_conn = settings.devops_max_connections
        return httpx.AsyncClient(
            base_url=settings.devops_api_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.bot_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(settings.devops_timeout_seconds),
            limits=httpx.Limits(
                max_connections=max_conn,
                max_keepalive_connections=max(1, max_conn // 2),
            ),
        )

    async def aclose(self) -> None:
        """Close the underlying client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "DevOpsClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send a request with retry/backoff and return decoded JSON."""
        retryer = AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(max(1, self._settings.devops_max_retries)),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type((httpx.TransportError, _RetryableStatusError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )
        try:
            async for attempt in retryer:
                with attempt:
                    response = await self._client.request(method, path, json=json, params=params)
                    if response.status_code in _RETRYABLE_STATUSES:
                        raise _RetryableStatusError(response)
                    response.raise_for_status()
                    return response.json()
        except _RetryableStatusError as exc:
            # Retries exhausted on a transient status: surface it as a real error.
            exc.response.raise_for_status()
        raise RuntimeError("unreachable: retry loop exited without a result")

    # --- API surface -------------------------------------------------------

    async def get_resources(self) -> Dict[str, Any]:
        """Fetch the bot's board resources (epics, features, stories, tasks)."""
        return await self._request("GET", "/bot/resources")

    async def update_node(
        self, node_type: str, node_id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a DevOps node (e.g. ``task``, ``epic``) with ``fields``."""
        return await self._request(
            "PUT", f"/devops/nodes/{node_type}/{node_id}", json=fields
        )

    async def create_task(
        self, title: str, description: str = "", story_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a task, optionally under a parent user story."""
        payload: Dict[str, Any] = {"title": title, "description": description}
        if story_id:
            payload["storyId"] = story_id
        return await self._request("POST", "/bot/tasks", json=payload)
