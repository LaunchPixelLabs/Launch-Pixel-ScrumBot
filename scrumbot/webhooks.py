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

    # --- WhatsApp inbound (Meta Cloud API) ---------------------------------

    @api.get("/webhooks/whatsapp")
    async def whatsapp_verify(request: Request):
        """Meta webhook verification handshake."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode == "subscribe" and token and token == settings.whatsapp_verify_token:
            logger.info("WhatsApp webhook verified.")
            # Meta expects the raw challenge echoed back as text/plain.
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(challenge or "")
        raise HTTPException(status_code=403, detail="verification failed")

    @api.post("/webhooks/whatsapp")
    async def whatsapp_receive(request: Request) -> dict:
        """Mirror inbound WhatsApp client messages into Discord."""
        payload = await request.json()
        for line in _extract_whatsapp_messages(payload):
            logger.info("WhatsApp inbound: %s", line)
            if notify is not None:
                msg = f"💬 **WhatsApp — Client Message**\n{line}"
                if app.queue is not None:
                    await app.queue.enqueue(notify, msg)
                else:
                    await notify(msg)
        return {"ok": True}

    # --- ACP: Agent Communication Protocol surface -------------------------
    # A minimal HTTP surface (sibling to the MCP server) so other agents/systems
    # can task the Scrum Master directly. Runs are authenticated with the webhook
    # secret because they can take real actions on the board/pipeline.

    @api.get("/acp/agents")
    async def acp_agents() -> dict:
        """Return this agent's ACP capability card."""
        return {
            "agents": [
                {
                    "name": "launchpixel-scrum-master",
                    "description": (
                        "Dual-Brain (Nemotron lead + Gemini) AI Scrum Master for "
                        "LaunchPixel: board, leads, finance, and business knowledge."
                    ),
                    "input_schema": {"type": "object", "properties": {"input": {"type": "string"}}},
                    "endpoints": {"run": "/acp/runs"},
                }
            ]
        }

    @api.post("/acp/runs")
    async def acp_run(
        request: Request,
        x_webhook_secret: Optional[str] = Header(default=None),
    ) -> dict:
        """Run the agent for an external caller and return the output (ACP-style)."""
        if settings.webhook_secret and x_webhook_secret != settings.webhook_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")
        body = await request.json()
        # Accept either {"input": "..."} or ACP-style {"inputs": [{"content": "..."}]}.
        text = body.get("input")
        if not text and isinstance(body.get("inputs"), list) and body["inputs"]:
            first = body["inputs"][0]
            text = first.get("content") if isinstance(first, dict) else str(first)
        if not text:
            raise HTTPException(status_code=400, detail="missing 'input'")
        thread_id = body.get("session_id") or body.get("thread_id") or "acp"
        try:
            output = await app.require_agent().ask(str(text), thread_id=str(thread_id))
        except Exception as exc:  # noqa: BLE001 - report to the caller
            logger.exception("ACP run failed")
            raise HTTPException(status_code=500, detail=str(exc))
        return {
            "run_id": thread_id,
            "status": "completed",
            "outputs": [{"role": "agent", "content": output}],
        }

    return api


def _extract_whatsapp_messages(payload: dict) -> list[str]:
    """Pull human-readable lines out of a Meta WhatsApp webhook payload."""
    lines: list[str] = []
    if payload.get("object") != "whatsapp_business_account":
        return lines
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            contacts = value.get("contacts", []) or []
            for message in value.get("messages", []) or []:
                sender = message.get("from", "Unknown")
                name = sender
                if contacts:
                    name = contacts[0].get("profile", {}).get("name", sender)
                mtype = message.get("type", "text")
                if mtype == "text":
                    body = message.get("text", {}).get("body", "")
                elif mtype == "button":
                    body = message.get("button", {}).get("text", "[Button Click]")
                else:
                    body = f"[{mtype.capitalize()} message]"
                lines.append(f"**{name}** ({sender}): {body}")
    return lines


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
