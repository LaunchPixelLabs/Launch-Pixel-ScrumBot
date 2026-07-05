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
    """Retrieve integration tools from Composio."""
    try:
        import os
        from scrumbot.config import get_settings
        # We pass API key if composio_api_key is in settings, else we rely on composio core to throw if missing
        api_key = get_settings().composio_api_key
        if api_key:
            toolset = ComposioToolSet(api_key=api_key)
        else:
            toolset = ComposioToolSet()
        # We can add explicit apps like GITHUB, JIRA or generic actions
        # For this agency Scrum Master, let's load all standard tools
        return toolset.get_tools()
    except ImportError:
        import logging
        logging.getLogger(__name__).warning("composio-langchain not installed or failed to initialize.")
        return []
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Composio failed to initialize: {e}")
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
