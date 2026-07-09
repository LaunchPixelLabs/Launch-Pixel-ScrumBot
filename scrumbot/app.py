"""Application container and lifecycle.

``ScrumBotApp`` is the composition root: it constructs every long-lived resource
once, wires them together, and tears them down cleanly. The Discord bot and the
MCP server are both handed the *same* started instance, so there is a single
LLM, a single pooled HTTP client, a single vector store and a single agent across
the whole process.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from scrumbot.agent import ScrumAgent, build_checkpointer
from scrumbot.brains import DualBrainCouncil
from scrumbot.config import Settings, get_settings
from scrumbot.custom_backend.client import DevOpsClient
from scrumbot.data.chroma import ChromaManager
from scrumbot.data.collector import DiscordChatCollector
from scrumbot.llm import get_llm
from scrumbot.queue import RequestQueue
from scrumbot.tools import get_all_tools

logger = logging.getLogger(__name__)


class ScrumBotApp:
    """Owns and wires the application's shared, long-lived resources."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.devops_client: Optional[DevOpsClient] = None
        self.chroma: Optional[ChromaManager] = None
        self.collector: Optional[DiscordChatCollector] = None
        self.council: Optional[DualBrainCouncil] = None
        self.agent: Optional[ScrumAgent] = None
        self.queue: Optional[RequestQueue] = None
        self._started = False

    async def startup(self) -> "ScrumBotApp":
        """Build resources and start background workers (idempotent)."""
        if self._started:
            return self

        logger.info(
            "Starting ScrumBotApp (dual_brain=%s, lead=%s, backup=%s)...",
            self.settings.enable_dual_brain,
            self.settings.primary_model,
            self.settings.secondary_model,
        )

        # Integrations + data layer.
        self.devops_client = DevOpsClient(self.settings)
        # Chroma + local embedding model init is CPU/IO heavy; keep it off the loop.
        self.chroma = await asyncio.to_thread(ChromaManager, self.settings)
        self.collector = DiscordChatCollector(self.chroma)

        # Seed the Business Brain scaffold (idempotent, best-effort, off-loop).
        if self.settings.seed_business_knowledge:
            await asyncio.to_thread(self._seed_knowledge)

        # Dual-Brain council: Nemotron leads (51%), Gemini backs & co-decides (49%).
        self.council = DualBrainCouncil.from_settings(self.settings)

        # Agent (Dual-Brain LLM + tools + memory).
        tools = get_all_tools(self.devops_client, self.collector, council=self.council)
        checkpointer = build_checkpointer(self.settings)
        if self.settings.enable_dual_brain:
            self.agent = ScrumAgent.dual_brain(
                self.council.primary,
                self.council.secondary,
                tools,
                checkpointer=checkpointer,
            )
        else:
            llm = get_llm(self.settings.scrum_agent_model, self.settings)
            self.agent = ScrumAgent(llm, tools, checkpointer=checkpointer)

        # Async work queue for offloading LLM turns off the Discord event loop.
        self.queue = RequestQueue(num_workers=self.settings.queue_workers)
        await self.queue.start()

        self._started = True
        logger.info("ScrumBotApp ready (%d tools, %d queue workers).",
                    len(tools), self.settings.queue_workers)
        return self

    async def shutdown(self) -> None:
        """Stop workers and release resources."""
        logger.info("Shutting down ScrumBotApp...")
        if self.queue is not None:
            await self.queue.stop()
        if self.devops_client is not None:
            await self.devops_client.aclose()
        self._started = False

    async def __aenter__(self) -> "ScrumBotApp":
        return await self.startup()

    async def __aexit__(self, *_exc: object) -> None:
        await self.shutdown()

    def require_agent(self) -> ScrumAgent:
        """Return the agent, raising if the app was not started."""
        if self.agent is None:
            raise RuntimeError("ScrumBotApp.startup() must be awaited before use.")
        return self.agent

    @staticmethod
    def _seed_knowledge() -> None:
        """Seed the starter business-knowledge scaffold (best-effort)."""
        try:
            from scrumbot.integrations.admin_db import seed_default_business_knowledge

            seeded = seed_default_business_knowledge()
            if seeded:
                logger.info("Seeded %d starter business-knowledge topics.", seeded)
        except Exception as exc:  # noqa: BLE001 - never block startup on the DB
            logger.warning("Business-knowledge seed skipped: %s", exc)
