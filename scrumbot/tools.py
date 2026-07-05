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


from langchain_core.tools import tool
from scrumbot.integrations.admin_db import get_company_knowledge, upsert_company_knowledge
from scrumbot.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

@tool
def ask_business_brain(query: str) -> str:
    """Consult the specialized Gemini Business Brain for LaunchPixel business strategy, SOPs, KPIs, and operational knowledge.
    
    Use this tool whenever you need deep business context or to answer a question that requires agency/company knowledge.
    """
    try:
        # 1. Fetch dynamic memory from NeonDB
        context = get_company_knowledge()
        
        # 2. Instantiate the Gemini "Business Brain"
        gemini_brain = get_llm(model_name="gemini-2.5-flash")
        
        # 3. Create the prompt combining the context and the user query
        messages = [
            SystemMessage(content=f"You are the LaunchPixel Business Brain. You know all about the company's SOPs, KPIs, and rules.\n\n{context}"),
            HumanMessage(content=query)
        ]
        
        # 4. Ask Gemini
        response = gemini_brain.invoke(messages)
        return response.content
    except Exception as e:
        return f"Error consulting Business Brain: {str(e)}"

@tool
def learn_business_rule(topic: str, content: str) -> str:
    """Save or update a business rule, SOP, or KPI into the LaunchPixel company knowledge database.
    
    Use this tool when the founder tells you to remember a new business rule, KPI, or SOP. 
    The topic should be a short, clear title (e.g. 'Project Kickoff SOP', 'Performance KPIs').
    """
    success = upsert_company_knowledge(topic, content)
    if success:
        return f"Successfully saved business knowledge under topic: {topic}"
    return f"Failed to save business knowledge for topic: {topic}"

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

from scrumbot.data.collector import DiscordChatCollector
from scrumbot.custom_backend.db_tools import get_neon_tools

def get_all_tools(devops_client: Optional[DevOpsClient] = None, chat_collector: Optional[DiscordChatCollector] = None) -> List[BaseTool]:
    """Assemble the full tool set for the agent.

    Args:
        devops_client: When provided, DevOps board tools bound to this client
            are included. When ``None`` (e.g. a research-only deployment) only
            the web tools are returned.
        chat_collector: When provided, enables the search_discord_history tool.
    """
    tools: List[BaseTool] = get_web_tools()
    
    # Add Neon DB tools for Discord Kanban
    tools.extend(get_neon_tools())
    
    # Add Composio Tools
    tools.extend(get_composio_tools())
    
    if devops_client is not None:
        tools.extend(get_devops_tools(devops_client))
        
    # Add Dual-Brain / Business Knowledge Tools
    tools.extend([ask_business_brain, learn_business_rule])
    
    if chat_collector is not None:
        @tool
        async def search_discord_history(query: str, limit: int = 5) -> str:
            """Search the Discord semantic memory for past conversations, messages, or decisions.
            
            Use this tool to recall context when a user asks about something discussed previously in Discord.
            """
            try:
                results = await chat_collector.search_messages(query, k=limit)
                if not results:
                    return "No relevant past messages found in Discord."
                formatted = []
                for doc in results:
                    author = doc.metadata.get("author", "Unknown")
                    date = doc.metadata.get("timestamp", "Unknown Date")
                    formatted.append(f"[{date}] {author}: {doc.page_content}")
                return "\n".join(formatted)
            except Exception as e:
                return f"Error searching Discord history: {str(e)}"
                
        tools.append(search_discord_history)
    
    # Catch tool exceptions so they return to the agent instead of crashing the run.
    from langchain_core.tools import StructuredTool
    
    safe_tools = []
    for t in tools:
        if isinstance(t, BaseTool):
            # Create a wrapper that safely catches ALL exceptions.
            def _make_safe_run(orig_run):
                def safe_run(*args, **kwargs):
                    try:
                        return orig_run(*args, **kwargs)
                    except NotImplementedError:
                        raise
                    except Exception as e:
                        return f"Tool Execution Error: {str(e)}"
                return safe_run
                
            def _make_safe_arun(orig_arun):
                async def safe_arun(*args, **kwargs):
                    try:
                        if orig_arun is None:
                            return None
                        return await orig_arun(*args, **kwargs)
                    except NotImplementedError:
                        raise
                    except Exception as e:
                        return f"Tool Execution Error: {str(e)}"
                return safe_arun
            
            t._run = _make_safe_run(t._run)
            if hasattr(t, "_arun") and getattr(t, "_arun", None) is not None:
                t._arun = _make_safe_arun(t._arun)
            
            safe_tools.append(t)
            
    return safe_tools
