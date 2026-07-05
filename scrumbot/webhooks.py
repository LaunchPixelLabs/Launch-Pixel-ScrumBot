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
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth

from scrumbot.app import ScrumBotApp
from scrumbot.config import get_settings
from scrumbot.custom_backend.sync import SyncCoordinator

logger = logging.getLogger(__name__)

oauth = OAuth()
oauth.register(
    name='discord',
    client_id=get_settings().discord_client_id,
    client_secret=get_settings().discord_client_secret,
    access_token_url='https://discord.com/api/oauth2/token',
    authorize_url='https://discord.com/api/oauth2/authorize',
    api_base_url='https://discord.com/api/v10/',
    client_kwargs={'scope': 'identify'},
)

Notifier = Callable[[str], Awaitable[None]]


def create_webhook_app(app: ScrumBotApp, notify: Optional[Notifier] = None) -> FastAPI:
    """Build the webhook FastAPI app bound to ``app`` and an optional notifier."""
    settings = get_settings()
    api = FastAPI(title="ScrumBot Webhooks", version="1.0.0")
    
    # We need sessions for OAuth
    api.add_middleware(SessionMiddleware, secret_key=settings.webhook_secret or "dev-secret-key")

    @api.get("/login/discord")
    async def login_discord(request: Request):
        redirect_uri = request.url_for("auth_discord")
        # Ensure it's https if behind a proxy
        redirect_uri = str(redirect_uri).replace("http://", "https://") if "localhost" not in str(redirect_uri) else redirect_uri
        return await oauth.discord.authorize_redirect(request, redirect_uri)

    @api.get("/auth/discord")
    async def auth_discord(request: Request):
        try:
            token = await oauth.discord.authorize_access_token(request)
            user = await oauth.discord.get('users/@me', token=token)
            user_info = user.json()
            request.session['user'] = user_info
            return RedirectResponse(url='/integrations')
        except Exception as e:
            logger.error(f"OAuth Error: {e}")
            return HTMLResponse(f"Authentication failed: {e}", status_code=400)

    @api.get("/integrations", response_class=HTMLResponse)
    async def integrations_gui(request: Request):
        user = request.session.get('user')
        if not user:
            return HTMLResponse(
                "<h2>LaunchPixel Integrations</h2><p>Please <a href='/login/discord'>Login with Discord</a></p>",
                status_code=401
            )
            
        html = f"""
        <html>
            <head>
                <title>LaunchPixel Integrations</title>
                <style>
                    body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; background: #1e1e1e; color: #fff; }}
                    .card {{ background: #2d2d2d; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                    .btn {{ background: #5865F2; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 10px; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h2>Welcome, {user.get('username')}</h2>
                    <p>Manage your LaunchPixel AI integrations below.</p>
                </div>
                <div class="card">
                    <h3>Composio Apps</h3>
                    <p>Connect the necessary apps (Gmail, Slack, Notion, GitHub) for the Scrum Master.</p>
                    <a href="https://app.composio.dev/" target="_blank" class="btn">Connect Apps in Composio</a>
                </div>
                <div class="card">
                    <h3>AI Brains</h3>
                    <p>✅ NVIDIA NIM (Nemotron Orchestrator)<br>✅ Google Gemini (Business Brain)</p>
                </div>
            </body>
        </html>
        """
        return HTMLResponse(content=html)

    @api.get("/")
    @api.get("/ping")
    @api.get("/health")
    async def health() -> dict:
        return {"status": "ok", "message": "pong"}

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
