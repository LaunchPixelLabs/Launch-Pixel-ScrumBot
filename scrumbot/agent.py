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
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from scrumbot.config import Settings, get_settings
from scrumbot.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def build_checkpointer():
    """Return a LangGraph checkpointer.

    Uses PostgreSQL when ``DATABASE_URL`` is configured (falling back to in-memory
    if the driver/connection is unavailable), otherwise an in-process
    ``MemorySaver``.
    """
    import os
    database_url = os.getenv("DATABASE_URL")
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
        llm: BaseChatModel,
        tools: Sequence[BaseTool],
        *,
        checkpointer: Any = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self._checkpointer = checkpointer
        self._agent = create_react_agent(
            llm,
            list(tools),
            prompt=system_prompt,
            checkpointer=checkpointer,
        )

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
