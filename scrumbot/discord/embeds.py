"""
Helper functions for creating Discord embeds.
"""
from typing import Any, Dict, List

import discord


def create_board_embed(sprint_name: str, tasks_summary: Dict[str, int]) -> discord.Embed:
    """
    Creates an embed showing an overview of the agile board.
    
    Args:
        sprint_name: The name of the current sprint.
        tasks_summary: A dictionary mapping column names to task counts.
    """
    embed = discord.Embed(
        title=f"Board Overview: {sprint_name}",
        description="Current status of the sprint.",
        color=discord.Color.blue()
    )
    for status, count in tasks_summary.items():
        embed.add_field(name=status, value=f"{count} tasks", inline=True)
    
    embed.set_footer(text="ScrumBot Agile Dashboard")
    return embed


def create_task_embed(task: Dict[str, Any]) -> discord.Embed:
    """
    Creates an embed representing a single task card.
    
    Args:
        task: A dictionary containing task details.
    """
    status = task.get("status", "To Do")
    if status.lower() == "done":
        color = discord.Color.green()
    elif status.lower() == "in progress":
        color = discord.Color.blue()
    elif status.lower() == "blocked":
        color = discord.Color.red()
    else:
        color = discord.Color.orange()
    
    embed = discord.Embed(
        title=f"[{task.get('id', 'N/A')}] {task.get('title', 'Untitled')}",
        description=task.get("description", "No description provided."),
        color=color
    )
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Assignee", value=task.get("assignee", "Unassigned"), inline=True)
    
    return embed


def create_standup_summary_embed(date_str: str, updates: List[Dict[str, str]]) -> discord.Embed:
    """
    Creates an embed summarizing the daily standup.
    
    Args:
        date_str: The date of the standup.
        updates: A list of dicts with 'user' and 'update' keys.
    """
    embed = discord.Embed(
        title=f"Standup Summary - {date_str}",
        color=discord.Color.purple()
    )
    
    for update in updates:
        embed.add_field(
            name=update.get("user", "Unknown User"),
            value=update.get("update", "No update provided."),
            inline=False
        )
        
    return embed
