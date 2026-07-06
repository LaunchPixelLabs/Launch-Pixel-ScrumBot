"""Universal entry point for AI ScrumBot.

Runs the Discord bot, the MCP server, or both against a single shared
application container:

    python main.py --mode discord   # Discord bot only (default)
    python main.py --mode mcp       # MCP server only (transport from env)
    python main.py --mode both      # bot + MCP (MCP forced to HTTP)

In "both" mode a stdio MCP transport would fight the Discord bot for
stdin/stdout, so it is transparently upgraded to HTTP.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from scrumbot.app import ScrumBotApp
from scrumbot.config import get_settings, setup_logging
from scrumbot.discord.bot import ScrumBot
from scrumbot.discord.dispatcher import chunk_message
from scrumbot.mcp_server.server import serve as serve_mcp
from scrumbot.webhooks import serve_webhooks

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI ScrumBot entry point")
    parser.add_argument(
        "--mode",
        choices=["discord", "mcp", "both"],
        default="discord",
        help="Which surface(s) to run (default: discord).",
    )
    return parser.parse_args()


import random
async def _autonomous_loop(bot: ScrumBot) -> None:
    settings = get_settings()
    channel_id = settings.autonomous_channel_id or settings.notify_channel_id
    if not channel_id or settings.autonomous_interval_minutes <= 0:
        logger.info("Autonomous mode disabled (no channel or interval <= 0).")
        return
        
    await bot.wait_until_ready()
    logger.info("Starting autonomous background loop (every %s mins) on channel %s", settings.autonomous_interval_minutes, channel_id)
    
    prompt = (
        "You are in autonomous background mode. Use your tools to check for new updates (emails, Slack, GitHub issues, Notion docs), "
        "track finances, manage resources, or find leads. If you discover anything actionable, important, or noteworthy, summarize it clearly for the team. "
        "If there are no meaningful updates, simply respond with exactly 'ALL_GOOD' and nothing else."
    )
    
    while not bot.is_closed():
        try:
            wait_mins = random.randint(1, 14)
            logger.info("Autonomous mode sleeping for %s minutes", wait_mins)
            await asyncio.sleep(wait_mins * 60)
            
            agent = bot.app.require_agent()
            reply = await agent.ask(prompt, thread_id="autonomous_loop")
            
            if "ALL_GOOD" not in reply:
                channel = bot.get_channel(channel_id)
                if channel:
                    for chunk in chunk_message(f"**🤖 Autonomous Report:**\n{reply}"):
                        await channel.send(chunk)
                else:
                    logger.warning("Autonomous channel %s not found.", channel_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Autonomous loop error: %s", e)

async def _run(mode: str) -> None:
    settings = get_settings()
    bot: ScrumBot | None = None

    async with ScrumBotApp(settings) as app:
        tasks: list[asyncio.Task] = []
        try:
            if mode in ("discord", "both"):
                if not settings.discord_token:
                    raise SystemExit("DISCORD_TOKEN is required to run the Discord bot.")
                bot = ScrumBot(app)
                tasks.append(asyncio.create_task(bot.start(settings.discord_token), name="discord"))
                tasks.append(asyncio.create_task(_autonomous_loop(bot), name="autonomous"))

            if mode in ("mcp", "both"):
                transport = settings.mcp_transport
                if mode == "both" and transport == "stdio":
                    logger.warning("stdio MCP cannot coexist with the Discord bot; using HTTP.")
                    transport = "http"
                tasks.append(
                    asyncio.create_task(
                        serve_mcp(app, transport, settings.mcp_host, settings.mcp_port),
                        name="mcp",
                    )
                )

            if mode == "both" and settings.webhook_secret:
                async def _notify(text: str) -> None:
                    if bot is None or settings.notify_channel_id is None:
                        return
                    channel = bot.get_channel(settings.notify_channel_id)
                    if channel is None:
                        logger.warning("Notify channel %s not found.", settings.notify_channel_id)
                        return
                    for chunk in chunk_message(text):
                        await channel.send(chunk)

                import os
                port = int(os.environ.get("PORT", settings.webhook_port))
                
                tasks.append(
                    asyncio.create_task(
                        serve_webhooks(
                            app, settings.webhook_host, port, notify=_notify
                        ),
                        name="webhooks",
                    )
                )

            # Run until the first surface exits (or errors), then unwind cleanly.
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if (exc := task.exception()) is not None:
                    raise exc
        finally:
            if bot is not None and not bot.is_closed():
                await bot.close()

async def _start_dummy_server() -> None:
    """Starts a dummy aiohttp server to satisfy Render Web Service requirements."""
    import os
    from aiohttp import web
    
    port = int(os.environ.get("PORT", 8080))
    
    async def handle_ping(request):
        return web.Response(text="pong")
        
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/ping", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Dummy web server running on port {port}")
    
    # Run forever (or until cancelled)
    while True:
        await asyncio.sleep(3600)

def main() -> None:
    setup_logging()
    args = _parse_args()
    try:
        async def run_all():
            import os
            
            is_render = bool(os.environ.get("RENDER") or os.environ.get("PORT"))
            will_start_webhooks = (args.mode == "both" and get_settings().webhook_secret)
            
            # If we are on Render and NOT starting webhooks, run the dummy server to satisfy Render's port binding rule.
            if is_render and not will_start_webhooks:
                await asyncio.gather(
                    _run(args.mode),
                    _start_dummy_server()
                )
            else:
                await _run(args.mode)
                
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Shutting down (interrupted).")


if __name__ == "__main__":
    main()
