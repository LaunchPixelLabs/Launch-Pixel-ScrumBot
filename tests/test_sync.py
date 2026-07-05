"""Tests for DevOps -> Discord event rendering (pure, no external deps)."""
from __future__ import annotations

from scrumbot.custom_backend.sync import SyncCoordinator


def test_format_event_reads_common_fields() -> None:
    message = SyncCoordinator.format_event(
        {
            "event": "task.updated",
            "node": {"title": "Fix login bug", "status": "Done"},
            "actor": "alice",
        }
    )
    assert "task.updated" in message
    assert "Fix login bug" in message
    assert "Done" in message
    assert "alice" in message


def test_format_event_is_defensive_about_shape() -> None:
    # Empty payload must not raise and should fall back gracefully.
    assert "an item" in SyncCoordinator.format_event({})


def test_format_event_handles_flat_payload() -> None:
    message = SyncCoordinator.format_event({"type": "epic.created", "name": "Billing"})
    assert "epic.created" in message
    assert "Billing" in message
