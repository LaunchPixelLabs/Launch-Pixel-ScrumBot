"""Core LangGraph ReAct agent.

The agent receives its LLM, tools and (optional) checkpointer via constructor
injection -- it no longer builds an LLM at import time, so importing the module
has no side effects and unit tests can pass fakes. When a checkpointer is present
the agent keeps per-thread conversation memory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from scrumbot.config import Settings, get_settings
from scrumbot.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def build_dual_brain_model(
    primary: BaseChatModel,
    secondary: Optional[BaseChatModel],
    tools: Sequence[BaseTool],
) -> Runnable:
    """Wire the two brains into a single model runnable for the agent.

    Nemotron (``primary``) leads every turn; Gemini (``secondary``) is bound with
    the same tools and registered as an automatic fallback, so a turn the lead
    brain botches (a malformed tool call, a transient NIM error) is transparently
    retried on the second brain rather than crashing the run. When there is no
    second brain the primary is returned unbound and the agent binds it itself.
    """
    if secondary is None:
        return primary
    tool_list = list(tools)
    lead = primary.bind_tools(tool_list)
    backup = secondary.bind_tools(tool_list)
    return lead.with_fallbacks([backup])


def build_checkpointer(settings: Optional[Settings] = None):
    """Return a LangGraph checkpointer.

    Uses PostgreSQL when ``DATABASE_URL`` is configured (falling back to in-memory
    if the driver/connection is unavailable), otherwise an in-process
    ``MemorySaver``.
    """
    settings = settings or get_settings()
    database_url = settings.database_url
    if database_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            logger.info("Using PostgreSQL checkpointer.")
            # Important: PostgresSaver must be used as a context manager or have its pool managed.
            # For simplicity in global scope, we return a configured saver if the pool is held open elsewhere.
            # In production, the app lifecycle should manage this pool.
            pool = ConnectionPool(conninfo=database_url, max_size=20)
            saver = PostgresSaver(pool)
            saver.setup()
            return saver
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("PostgreSQL checkpointer unavailable (%s); using in-memory.", exc)

    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


class ScrumAgent:
    """Thin wrapper around a LangGraph ReAct agent."""

    def __init__(
        self,
        llm: "BaseChatModel | Runnable",
        tools: Sequence[BaseTool],
        *,
        checkpointer: Any = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        # ``llm`` may be a plain chat model (create_react_agent binds the tools
        # for us) or an already-tool-bound runnable such as the dual-brain
        # fallback chain from :func:`build_dual_brain_model` (used as-is).
        self._checkpointer = checkpointer
        self._agent = create_react_agent(
            llm,
            list(tools),
            prompt=system_prompt,
            checkpointer=checkpointer,
        )

    @classmethod
    def dual_brain(
        cls,
        primary: BaseChatModel,
        secondary: Optional[BaseChatModel],
        tools: Sequence[BaseTool],
        *,
        checkpointer: Any = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> "ScrumAgent":
        """Build a ScrumAgent whose model is the Nemotron-lead / Gemini-backup council."""
        model = build_dual_brain_model(primary, secondary, tools)
        return cls(model, tools, checkpointer=checkpointer, system_prompt=system_prompt)

    async def invoke(
        self,
        messages: List[BaseMessage],
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Run the agent over ``messages`` and return the final graph state."""
        return await self._agent.ainvoke({"messages": messages}, config=config, **kwargs)

    async def ask(self, text: str, thread_id: Optional[str] = None) -> str:
        """Convenience helper: ask a single question, return the reply text.

        ``thread_id`` scopes conversation memory (e.g. a Discord channel id). When
        a checkpointer is configured a thread id is always supplied so LangGraph
        can persist state.
        """
        config: Optional[Dict[str, Any]] = None
        if self._checkpointer is not None:
            config = {"configurable": {"thread_id": thread_id or "default"}}
        elif thread_id:
            config = {"configurable": {"thread_id": thread_id}}

        result = await self.invoke([HumanMessage(content=text)], config=config)
        messages = result.get("messages", [])
        return messages[-1].content if messages else ""
