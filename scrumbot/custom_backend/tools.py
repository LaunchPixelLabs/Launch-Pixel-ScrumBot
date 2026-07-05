"""LangChain tools for the DevOps board.

Exposed as a factory (`get_devops_tools`) bound to an injected client rather than
a module-level singleton, so there are no import-time side effects and the tools
are trivial to test with a fake client. Every tool catches backend failures and
returns a structured ``{"error": ...}`` payload, which lets the agent reason
about the failure instead of the whole run raising.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.tools import BaseTool, tool

from .client import DevOpsClient

logger = logging.getLogger(__name__)


async def _call(fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """Await ``fn`` and convert any exception into an error payload."""
    try:
        return await fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - deliberately surfaced to the agent
        logger.warning("DevOps API call failed: %s", exc)
        return {"error": str(exc)}


def get_devops_tools(client: DevOpsClient) -> List[BaseTool]:
    """Build the DevOps tool set bound to ``client``."""

    @tool
    async def devops_get_board_overview() -> Dict[str, Any]:
        """Get a full overview of the DevOps board (epics, features, stories, tasks)."""
        return await _call(client.get_resources)

    @tool
    async def devops_list_epics() -> Dict[str, Any]:
        """List all epics on the DevOps board."""
        res = await _call(client.get_resources)
        if isinstance(res, dict) and "error" in res:
            return res
        return {"epics": res.get("epics", [])}

    @tool
    async def devops_list_tasks() -> Dict[str, Any]:
        """List all tasks on the DevOps board."""
        res = await _call(client.get_resources)
        if isinstance(res, dict) and "error" in res:
            return res
        return {"tasks": res.get("tasks", [])}

    @tool
    async def devops_update_task_status(task_id: str, status: str) -> Dict[str, Any]:
        """Update the status of a task (e.g. 'In Progress', 'Done', 'Blocked')."""
        return await _call(client.update_node, "task", task_id, {"status": status})

    @tool
    async def devops_create_task(
        title: str, description: str = "", story_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new task, optionally under a parent user story id."""
        return await _call(client.create_task, title, description, story_id)

    return [
        devops_get_board_overview,
        devops_list_epics,
        devops_list_tasks,
        devops_update_task_status,
        devops_create_task,
    ]
