"""Two-way synchronisation between Discord and the DevOps board.

* **Discord -> DevOps** is handled by the agent's ``devops_*`` tools: a user asks
  the bot to create/update work and the agent calls the REST API.
* **DevOps -> Discord** is handled by the webhook receiver (``scrumbot.webhooks``),
  which renders an inbound event with :meth:`SyncCoordinator.format_event` and
  announces it in the notify channel.

This module holds the (pure, easily-tested) rendering logic for that second
direction.
"""
from __future__ import annotations

from typing import Any, Dict


class SyncCoordinator:
    """Renders DevOps board events into Discord-friendly messages."""

    @staticmethod
    def format_event(payload: Dict[str, Any]) -> str:
        """Turn a webhook payload into a concise Discord message.

        Defensive about shape: the backend may nest the node under ``node`` or
        ``data`` and use different key names, so we probe a few common ones.
        """
        event = payload.get("event") or payload.get("type") or "update"
        node = payload.get("node") or payload.get("data") or payload
        title = (
            node.get("title")
            or node.get("name")
            or node.get("subject")
            or node.get("id")
            or "an item"
        )

        parts = [f"**DevOps {event}** — {title}"]
        if status := node.get("status"):
            parts.append(f"status: `{status}`")
        if actor := (payload.get("actor") or node.get("assignee")):
            parts.append(f"by {actor}")
        return " · ".join(parts)
