"""Bridges Discord interactions to the agent.

Slash-command handlers here are the coroutines the work queue runs. Each turns a
command into an instruction for the agent, then edits the (already-deferred)
interaction with the reply, chunked to respect Discord's 2000-character limit.
This is what closes the async loop: command -> queue -> agent -> reply.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import discord

from scrumbot.app import ScrumBotApp

logger = logging.getLogger(__name__)

_MAX_LEN = 1990  # a little under Discord's 2000 hard limit


def chunk_message(text: str, size: int = _MAX_LEN) -> List[str]:
    """Split ``text`` into <=``size`` pieces, preferring line boundaries."""
    text = text or "(no response)"
    if len(text) <= size:
        return [text]

    chunks: List[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > size:
            if current:
                chunks.append(current)
                current = ""
            while len(line) > size:  # a single very long line
                chunks.append(line[:size])
                line = line[size:]
        current += line
    if current:
        chunks.append(current)
    return chunks


class Dispatcher:
    """Translates slash commands into agent runs and posts the results."""

    def __init__(self, app: ScrumBotApp) -> None:
        self._app = app

    async def _respond(self, interaction: discord.Interaction, instruction: str) -> None:
        agent = self._app.require_agent()
        try:
            reply = await agent.ask(instruction, thread_id=str(interaction.channel_id))
        except Exception as exc:  # noqa: BLE001 - report failures to the user
            logger.exception("Agent run failed")
            reply = f":warning: Something went wrong while processing that: {exc}"
        for chunk in chunk_message(reply):
            await interaction.followup.send(chunk)

    # --- command handlers (run on the work queue) --------------------------

    async def handle_ask(self, interaction: discord.Interaction, question: str) -> None:
        await self._respond(interaction, question)

    async def handle_board(self, interaction: discord.Interaction) -> None:
        await self._respond(
            interaction,
            "Give a concise overview of the current DevOps board: list active epics "
            "and task counts grouped by status.",
        )

    async def handle_standup(self, interaction: discord.Interaction) -> None:
        await self._respond(
            interaction,
            "Produce today's standup summary from recent board activity. Reference "
            "the relevant task ids.",
        )

    async def handle_task_update(
        self, interaction: discord.Interaction, task_id: str, status: str
    ) -> None:
        await self._respond(
            interaction,
            f"Update the task with id '{task_id}' to status '{status}' using the "
            "DevOps tools, then confirm the result.",
        )

    async def handle_task_create(
        self, interaction: discord.Interaction, title: str, description: Optional[str]
    ) -> None:
        await self._respond(
            interaction,
            f"Create a new DevOps task titled '{title}' with description "
            f"'{description or ''}'. Then confirm with the created task's details.",
        )

    async def handle_sync(self, interaction: discord.Interaction) -> None:
        await self._respond(
            interaction,
            "Fetch the latest DevOps board overview to confirm connectivity and "
            "summarise the current state.",
        )

    async def handle_clear(self, interaction: discord.Interaction) -> None:
        await self._respond(
            interaction,
            "List all tasks whose status is 'Done' so they can be archived, and "
            "summarise them.",
        )
