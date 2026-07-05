"""DevOps backend integration package.

Re-exports are lazy (PEP 562) so importing a light submodule (e.g. ``sync``)
doesn't drag in ``httpx`` or the rest of the client stack.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["DevOpsClient", "get_devops_tools", "SyncCoordinator"]

if TYPE_CHECKING:
    from .client import DevOpsClient
    from .sync import SyncCoordinator
    from .tools import get_devops_tools


def __getattr__(name: str) -> Any:
    if name == "DevOpsClient":
        from .client import DevOpsClient

        return DevOpsClient
    if name == "get_devops_tools":
        from .tools import get_devops_tools

        return get_devops_tools
    if name == "SyncCoordinator":
        from .sync import SyncCoordinator

        return SyncCoordinator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
