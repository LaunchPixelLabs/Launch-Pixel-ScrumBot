"""Discord bot.

Slash commands defer immediately and enqueue the real work onto the shared
async queue; a worker runs the agent and edits the deferred response. Nothing
blocks the gateway event loop.
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from scrumbot.app import ScrumBotApp
from scrumbot.discord.dispatcher import Dispatcher

logger = logging.getLogger(__name__)


class ScrumCommands(commands.Cog):
    """Slash commands for ScrumBot. Each defers, then enqueues a dispatcher job."""

    def __init__(self, bot: "ScrumBot") -> None:
        self.bot = bot

    @property
    def _queue(self):
        return self.bot.app.queue

    @property
    def _dispatch(self) -> Dispatcher:
        return self.bot.dispatcher

    @app_commands.command(name="ask", description="Ask the Scrum Master a question.")
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(self._dispatch.handle_ask, interaction, question)

    @app_commands.command(name="board", description="View the current agile board.")
    async def board(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(self._dispatch.handle_board, interaction)

    @app_commands.command(name="standup", description="Generate the daily standup summary.")
    async def standup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(self._dispatch.handle_standup, interaction)

    task_group = app_commands.Group(name="task", description="Task management commands.")

    @task_group.command(name="update", description="Update a task's status.")
    async def task_update(
        self, interaction: discord.Interaction, task_id: str, status: str
    ) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(
            self._dispatch.handle_task_update, interaction, task_id, status
        )

    @task_group.command(name="create", description="Create a new task.")
    async def task_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(
            self._dispatch.handle_task_create, interaction, title, description
        )

    @app_commands.command(name="sync", description="Sync board with external trackers.")
    async def sync(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(self._dispatch.handle_sync, interaction)

    @app_commands.command(name="clear", description="Summarise completed tasks to clear.")
    async def clear(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await self._queue.enqueue(self._dispatch.handle_clear, interaction)


class ScrumBot(commands.Bot):
    """The Discord bot, bound to a started :class:`ScrumBotApp`."""

    def __init__(self, app: ScrumBotApp, *args, **kwargs) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        # LaunchPixelCog ships a custom `!help`; disable discord.py's default help
        # command so the two don't collide during add_cog.
        super().__init__(
            *args, command_prefix="!", intents=intents, help_command=None, **kwargs
        )
        self.app = app
        self.dispatcher = Dispatcher(app)

    async def setup_hook(self) -> None:
        from scrumbot.discord.events import setup_events
        from scrumbot.discord.scheduler import setup_scheduler
        from scrumbot.discord.launchpixel_cog import LaunchPixelCog

        setup_events(self)
        await setup_scheduler(self)
        await self.add_cog(ScrumCommands(self))
        await self.add_cog(LaunchPixelCog(self))
        await self.tree.sync()
        logger.info("ScrumBot setup complete.")
