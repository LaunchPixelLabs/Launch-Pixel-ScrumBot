"""Inbound webhook receiver: DevOps board -> Discord.

A tiny FastAPI app that authenticates requests with a shared secret and forwards
each board event to Discord via an injected ``notify`` coroutine. This closes the
DevOps -> Discord half of the sync story (the other half lives in the agent's
tools).
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Header, HTTPException, Request

from scrumbot.app import ScrumBotApp
from scrumbot.config import get_settings
from scrumbot.custom_backend.sync import SyncCoordinator

logger = logging.getLogger(__name__)

Notifier = Callable[[str], Awaitable[None]]


def create_webhook_app(app: ScrumBotApp, notify: Optional[Notifier] = None) -> FastAPI:
    """Build the webhook FastAPI app bound to ``app`` and an optional notifier."""
    settings = get_settings()
    api = FastAPI(title="ScrumBot Webhooks", version="1.0.0")

    @api.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @api.post("/webhooks/devops")
    async def devops_webhook(
        request: Request,
        x_webhook_secret: Optional[str] = Header(default=None),
    ) -> dict:
        if settings.webhook_secret and x_webhook_secret != settings.webhook_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")

        payload = await request.json()
        message = SyncCoordinator.format_event(payload)
        logger.info("DevOps webhook: %s", message)

        if notify is not None:
            # Offload delivery so a slow Discord send never stalls the ack.
            if app.queue is not None:
                await app.queue.enqueue(notify, message)
            else:
                await notify(message)
        return {"ok": True}

    return api


async def serve_webhooks(
    app: ScrumBotApp,
    host: str,
    port: int,
    notify: Optional[Notifier] = None,
) -> None:
    """Run the webhook receiver (awaitable, cancellable)."""
    import uvicorn

    fastapi_app = create_webhook_app(app, notify=notify)
    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info", loop="asyncio")
    server = uvicorn.Server(config)
    logger.info("Starting webhook receiver on %s:%d ...", host, port)
    await server.serve()
