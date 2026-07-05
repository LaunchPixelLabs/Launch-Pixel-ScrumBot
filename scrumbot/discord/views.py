"""
Discord UI View classes for interactive components.
"""
from typing import Awaitable, Callable, Optional

import discord


class TaskView(discord.ui.View):
    """A view containing buttons to manage a task."""

    def __init__(self, task_id: str, callback_func: Optional[Callable[[discord.Interaction, str, str], Awaitable[None]]] = None):
        """
        Args:
            task_id: The ID of the task being managed.
            callback_func: A callback to handle the button press.
                           It receives (interaction, task_id, action).
        """
        super().__init__(timeout=None)
        self.task_id = task_id
        self.callback_func = callback_func

    @discord.ui.button(label="Mark Done", style=discord.ButtonStyle.success, custom_id="task_done")
    async def mark_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to mark a task as done."""
        if self.callback_func:
            await self.callback_func(interaction, self.task_id, "done")
        else:
            await interaction.response.send_message(f"Task {self.task_id} marked as done!", ephemeral=True)

    @discord.ui.button(label="Set Blocked", style=discord.ButtonStyle.danger, custom_id="task_blocked")
    async def set_blocked(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to mark a task as blocked."""
        if self.callback_func:
            await self.callback_func(interaction, self.task_id, "blocked")
        else:
            await interaction.response.send_message(f"Task {self.task_id} set as blocked!", ephemeral=True)

    @discord.ui.button(label="In Progress", style=discord.ButtonStyle.primary, custom_id="task_progress")
    async def in_progress(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to mark a task as in progress."""
        if self.callback_func:
            await self.callback_func(interaction, self.task_id, "in_progress")
        else:
            await interaction.response.send_message(f"Task {self.task_id} moved to in progress!", ephemeral=True)
