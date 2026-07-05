"""Expose ScrumBot as an MCP server.

The server is built lazily from a started :class:`ScrumBotApp` (no agent is
constructed at import time), and can run over stdio (for local tool clients) or
HTTP/SSE (so it can run alongside the Discord bot).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from scrumbot.app import ScrumBotApp
from scrumbot.config import get_settings

logger = logging.getLogger(__name__)


def create_mcp_server(app: ScrumBotApp) -> FastMCP:
    """Build a FastMCP server whose tools delegate to ``app``."""
    mcp: FastMCP = FastMCP(
        "ScrumBot",
        instructions="Query the DevOps board and Discord history through the ScrumBot agent.",
    )

    @mcp.tool()
    async def ask_scrum_bot(query: str) -> str:
        """Ask the ScrumBot agent a question or give it a task about the board or chat."""
        return await app.require_agent().ask(query)

    @mcp.tool()
    async def search_discord_history(query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search over previously collected Discord messages."""
        if app.collector is None:
            return []
        docs = await app.collector.search_messages(query, k=limit)
        return [{"content": doc.page_content, **doc.metadata} for doc in docs]

    return mcp


async def serve(app: ScrumBotApp, transport: str, host: str, port: int) -> None:
    """Run the MCP server against an already-started ``app`` (awaitable)."""
    mcp = create_mcp_server(app)
    transport_kwargs: Dict[str, Any] = {}
    if transport in ("http", "sse"):
        transport_kwargs = {"host": host, "port": port}
    logger.info("Starting MCP server (transport=%s)...", transport)
    await mcp.run_async(transport=transport, **transport_kwargs)


def run(transport: Optional[str] = None) -> None:
    """Standalone entry point: build the app, then serve (blocking)."""
    settings = get_settings()
    resolved = transport or settings.mcp_transport

    async def _main() -> None:
        async with ScrumBotApp(settings) as app:
            await serve(app, resolved, settings.mcp_host, settings.mcp_port)

    asyncio.run(_main())
