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
from scrumbot.prompts import AUTONOMOUS_FOCUS_ORDER, build_autonomous_prompt


def _report_signature(text: str) -> str:
    """Normalise a report into a de-dup signature (lowercase, first content line).

    The autonomous loop re-runs each focus every few minutes; without this it would
    spam the same finding cycle after cycle. The signature is intentionally coarse
    (first meaningful line, stripped of markdown/emoji) so near-identical repeats
    collapse together while genuinely different reports still get through.
    """
    for raw in (text or "").splitlines():
        line = raw.strip().lower()
        if not line:
            continue
        # Drop markdown emphasis, emojis and the leading "Decision:"-style label so
        # "Decision: do X" and "Decision:  do X" hash the same.
        for ch in "*_#>`":
            line = line.replace(ch, "")
        line = " ".join(line.split())
        if len(line) >= 6:  # ignore bare headers like "1. decision:"
            return line[:200]
    return (text or "").strip().lower()[:200]


async def _autonomous_loop(bot: ScrumBot) -> None:
    """The 24/7 background shift.

    Each wake-up works ONE focus (briefing -> leads -> accountability -> blockers ->
    business-intel -> finance -> ...), so over a full cycle the bot touches every
    aspect of the business instead of asking one generic question forever. Lead
    reports go to the leads channel when configured; everything else goes to the
    autonomous/notify channel. A report ledger suppresses repeats within 12 hours so
    the team isn't spammed with the same finding cycle after cycle.
    """
    from scrumbot.integrations import admin_db

    settings = get_settings()
    channel_id = settings.autonomous_channel_id or settings.notify_channel_id
    if not channel_id or settings.autonomous_interval_minutes <= 0:
        logger.info("Autonomous mode disabled (no channel or interval <= 0).")
        return

    await bot.wait_until_ready()
    lo = max(1, settings.autonomous_min_minutes)
    hi = max(lo, settings.autonomous_max_minutes)
    logger.info(
        "Starting autonomous 24/7 loop (every %d-%d mins) on channel %s; focuses=%s",
        lo, hi, channel_id, ", ".join(AUTONOMOUS_FOCUS_ORDER),
    )

    focus_index = 0
    while not bot.is_closed():
        try:
            wait_mins = random.randint(lo, hi)
            logger.info("Autonomous mode sleeping for %s minutes", wait_mins)
            await asyncio.sleep(wait_mins * 60)

            focus = AUTONOMOUS_FOCUS_ORDER[focus_index % len(AUTONOMOUS_FOCUS_ORDER)]
            focus_index += 1
            logger.info("Autonomous cycle focus: %s", focus)

            agent = bot.app.require_agent()
            reply = await agent.ask(
                build_autonomous_prompt(focus),
                thread_id=f"autonomous_{focus}",
            )

            if not reply or "ALL_GOOD" in reply:
                continue

            # De-dup: skip if we already reported this same thing recently.
            signature = _report_signature(reply)
            try:
                already = await asyncio.to_thread(
                    admin_db.was_reported_recently, focus, signature, 12
                )
            except Exception as exc:  # noqa: BLE001 - never block a report on the DB
                logger.warning("Report-ledger check failed: %s", exc)
                already = False
            if already:
                logger.info("Autonomous %s report suppressed (duplicate): %s", focus, signature[:80])
                continue

            # Route lead findings to the dedicated leads channel if set; every
            # other focus gets a distinct emoji header for visual scanning.
            target_id = channel_id
            focus_headers = {
                "morning_briefing": "**☕ Morning Business Briefing:**",
                "leads": "**📩 Lead Scan:**",
                "competitive_intel": "**🔍 Competitive Intelligence:**",
                "accountability": "**📋 Accountability Check:**",
                "team_velocity": "**⚡ Team Velocity:**",
                "blockers": "**🚧 Blocker Sweep:**",
                "client_health": "**❤️ Client Health:**",
                "business_intel": "**📊 Business Intelligence:**",
                "revenue_ops": "**💰 Revenue Operations:**",
                "knowledge_gap": "**🧠 Knowledge & Learning:**",
                "finance": "**💸 Finance & Burn:**",
            }
            header = focus_headers.get(
                focus,
                f"**🤖 Autonomous Report — {focus.replace('_', ' ').title()}:**",
            )
            if focus == "leads" and settings.leads_channel_id:
                target_id = settings.leads_channel_id

            channel = bot.get_channel(target_id) or bot.get_channel(channel_id)
            if channel:
                for chunk in chunk_message(f"{header}\n{reply}"):
                    await channel.send(chunk)
                try:
                    await asyncio.to_thread(admin_db.record_report, focus, signature, reply)
                except Exception as exc:  # noqa: BLE001 - best-effort
                    logger.warning("Failed to record report: %s", exc)
            else:
                logger.warning("Autonomous target channel %s not found.", target_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Autonomous loop error: %s", e)


async def _founder_alert_loop(bot: ScrumBot) -> None:
    """Deliver queued founder escalations.

    The agent and the schedulers write alerts to ``founder_alerts`` (they have no
    Discord access); this loop is the single delivery path. Every ~60s it drains
    undelivered alerts:
      * high/critical -> @mention in the channel AND a DM to the founder
      * medium        -> @mention in the channel only
      * low           -> logged only (no ping)
    The loop is a no-op when no founder id or channel is configured.
    """
    from scrumbot.integrations import admin_db

    settings = get_settings()
    founder_id = settings.founder_discord_id
    channel_id = settings.autonomous_channel_id or settings.notify_channel_id
    if not founder_id or not channel_id:
        logger.info(
            "Founder alert loop disabled (founder_id=%s, channel_id=%s).",
            founder_id, channel_id,
        )
        return

    await bot.wait_until_ready()
    logger.info("Founder alert loop running (founder=%s, channel=%s).", founder_id, channel_id)

    while not bot.is_closed():
        try:
            await asyncio.sleep(60)
            alerts = await asyncio.to_thread(admin_db.get_undelivered_alerts, 20)
            if not alerts:
                continue

            channel = bot.get_channel(channel_id)
            founder_mention = f"<@{founder_id}>"

            for a in alerts:
                severity = (a.get("severity") or "medium").lower()
                topic = a.get("topic") or "Alert"
                summary = a.get("summary") or ""
                alert_id = a.get("id")
                if alert_id is None:
                    continue  # malformed row; nothing to deliver or mark

                # Always try to ping the channel for medium+ severity.
                if severity in ("medium", "high", "critical"):
                    if channel is not None:
                        icon = {"critical": "🚨", "high": "⚠️", "medium": "📍"}.get(severity, "📍")
                        line = (
                            f"{icon} **Founder Escalation ({severity.upper()})** {founder_mention}\n"
                            f"**{topic}**\n{summary}"
                        )
                        try:
                            for chunk in chunk_message(line):
                                await channel.send(chunk)
                        except Exception as exc:  # noqa: BLE001 - keep draining
                            logger.warning("Failed to post alert %s to channel: %s", alert_id, exc)
                    else:
                        logger.warning("Channel %s not cached; alert %s channel post skipped.", channel_id, alert_id)

                # High/critical also get a DM so nothing urgent is missed in channel noise.
                if severity in ("high", "critical"):
                    try:
                        user = await bot.fetch_user(founder_id)
                        if user is not None:
                            dm = (
                                f"🚨 **LaunchPixel escalation ({severity})**\n"
                                f"**{topic}**\n{summary}"
                            )
                            for chunk in chunk_message(dm):
                                await user.send(chunk)
                    except Exception as exc:  # noqa: BLE001 - DM is best-effort
                        logger.warning("Failed to DM founder for alert %s: %s", alert_id, exc)
                elif severity == "low":
                    logger.info("Low-severity alert %s logged (no ping): %s", alert_id, topic)

                # Mark delivered regardless of channel/DM hiccups so a bad row can't
                # re-ping forever; the log captures any delivery failure above.
                try:
                    await asyncio.to_thread(admin_db.mark_alert_delivered, alert_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to mark alert %s delivered: %s", alert_id, exc)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 - the loop must stay alive
            logger.error("Founder alert loop error: %s", exc)


async def _keepalive_loop(_bot: ScrumBot) -> None:
    """Self-ping the Render URL every 10 minutes so the free tier never sleeps.

    GitHub Actions is the primary keep-alive pinger, but this is a backup that
    runs inside the bot itself — if Actions is ever down or rate-limited, the
    bot still pings its own public URL. A no-op when ``KEEPALIVE_URL`` is unset.
    """
    import os

    settings = get_settings()
    url = settings.keepalive_url or os.environ.get("KEEPALIVE_URL")
    if not url:
        logger.info("Keep-alive loop disabled (no KEEPALIVE_URL).")
        return

    url = url.rstrip("/")
    logger.info("Keep-alive loop running -> %s", url)
    while not _bot.is_closed():
        try:
            await asyncio.sleep(600)  # 10 minutes
            await asyncio.to_thread(_ping_url, url)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 - the loop must stay alive
            logger.warning("Keep-alive ping failed: %s", exc)


def _ping_url(url: str) -> None:
    """Best-effort HTTP GET to keep the Render service warm."""
    import urllib.request

    for path in ("/health", "/ping", "/"):
        try:
            req = urllib.request.Request(f"{url}{path}", headers={"User-Agent": "scrumbot-keepalive"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info("Keep-alive OK (%s%s -> %s)", url, path, resp.status)
                return
        except Exception:  # noqa: BLE001 - try the next path
            continue
    logger.warning("Keep-alive: all paths failed for %s", url)

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
                tasks.append(asyncio.create_task(_founder_alert_loop(bot), name="founder_alerts"))
                tasks.append(asyncio.create_task(_keepalive_loop(bot), name="keepalive"))

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
