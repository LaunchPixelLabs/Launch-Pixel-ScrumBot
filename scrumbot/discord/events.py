"""Discord event handlers.

Besides readiness logging, ``on_message`` collects human messages into the
vector store (fire-and-forget, off the event loop) so they become searchable
context for the agent.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Set

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


async def _collect(collector, message: discord.Message) -> None:
    try:
        await collector.save_message(
            message_id=str(message.id),
            author=getattr(message.author, "display_name", str(message.author)),
            content=message.content,
            timestamp=message.created_at.isoformat(),
            channel=str(message.channel.id),
        )
    except Exception:  # noqa: BLE001 - collection is best-effort
        logger.exception("Failed to collect message %s", message.id)


def setup_events(bot: commands.Bot) -> None:
    """Register event listeners on ``bot``."""
    # Hold strong refs to background tasks so they aren't GC'd mid-flight.
    pending: Set[asyncio.Task] = set()

    @bot.event
    async def on_ready() -> None:
        logger.info("Logged in as %s (ID: %s)", bot.user, getattr(bot.user, "id", "?"))

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author != bot.user and message.content.strip():
            collector = getattr(bot.app, "collector", None)
            if collector is not None:
                task = asyncio.create_task(_collect(collector, message))
                pending.add(task)
                task.add_done_callback(pending.discard)
        await bot.process_commands(message)
