"""Central tool registry.

Combines stateless web-research tools with the stateful DevOps tools. The DevOps
client is injected (built and owned by the application container) so tools share
its pooled HTTP connection.
"""
from __future__ import annotations

from typing import List, Optional

from langchain_community.tools.arxiv.tool import ArxivQueryRun
from langchain_community.tools.ddg_search.tool import DuckDuckGoSearchRun
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_community.utilities.arxiv import ArxivAPIWrapper
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
from langchain_core.tools import BaseTool

from scrumbot.custom_backend.client import DevOpsClient
from scrumbot.custom_backend.tools import get_devops_tools


def get_web_tools() -> List[BaseTool]:
    """Stateless research tools: web search, arXiv, Wikipedia."""
    return [
        DuckDuckGoSearchRun(),
        ArxivQueryRun(api_wrapper=ArxivAPIWrapper()),
        WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()),
    ]


from scrumbot.custom_backend.db_tools import get_neon_tools

def get_composio_tools() -> List[BaseTool]:
    """Retrieve integration tools from Composio, if configured.

    Composio is fully optional; the agent is complete without it. Tools only
    load when ``COMPOSIO_API_KEY``, ``COMPOSIO_USER_ID`` and
    ``COMPOSIO_TOOLKITS`` are all set (a user id with connected accounts is
    required to enumerate real tools). We support the modern provider-based SDK
    and fall back to the legacy ``ComposioToolSet``; any failure degrades to an
    empty list rather than crashing app startup.
    """
    import logging

    from scrumbot.config import get_settings

    log = logging.getLogger(__name__)
    settings = get_settings()
    api_key = settings.composio_api_key
    if not api_key or not settings.composio_user_id or not settings.composio_toolkits:
        log.info("Composio not fully configured (need API key, user id, toolkits); skipping.")
        return []

    toolkits = [t.strip().upper() for t in settings.composio_toolkits.split(",") if t.strip()]

    # Modern provider-based SDK (composio + composio-langchain >= 0.8).
    try:
        from composio import Composio
        from composio_langchain import LangchainProvider

        client = Composio(api_key=api_key, provider=LangchainProvider())
        tools = client.tools.get(user_id=settings.composio_user_id, toolkits=toolkits)
        log.info("Loaded %d Composio tools for toolkits=%s", len(tools), toolkits)
        return list(tools)
    except ImportError:
        pass  # fall through to legacy API
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        log.warning("Composio (modern SDK) init failed: %s", exc)
        return []

    # Legacy ToolSet API (composio-langchain < 0.8).
    try:
        from composio_langchain import ComposioToolSet

        toolset = ComposioToolSet(api_key=api_key)
        return list(toolset.get_tools(apps=toolkits))
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        log.warning("Composio (legacy SDK) unavailable: %s", exc)
        return []

def get_all_tools(devops_client: Optional[DevOpsClient] = None) -> List[BaseTool]:
    """Assemble the full tool set for the agent.

    Args:
        devops_client: When provided, DevOps board tools bound to this client
            are included. When ``None`` (e.g. a research-only deployment) only
            the web tools are returned.
    """
    tools: List[BaseTool] = get_web_tools()
    
    # Add Neon DB tools for Discord Kanban
    tools.extend(get_neon_tools())
    
    # Add Composio Tools
    tools.extend(get_composio_tools())
    
    if devops_client is not None:
        tools.extend(get_devops_tools(devops_client))
    return tools
