"""Dual-Brain council: Nemotron leads, Gemini co-decides.

LaunchPixel's Scrum Master thinks with two brains at once:

* **Nemotron** (NVIDIA NIM) is the *lead* brain, weighted ``primary_weight``
  (0.51 by default). It drives every reasoning and tool-calling turn of the
  LangGraph agent.
* **Gemini** is the *second* brain, weighted ``secondary_weight`` (0.49). It is
  the automatic fallback for any turn the lead brain fails (which also fixes the
  historical NIM tool-calling flakiness), and the co-voter consulted for
  high-stakes business decisions.

Two collaboration modes are provided:

``build_council`` builds the two chat models (degrading to Gemini-only when no
NVIDIA key is present, so the bot always boots).

``DualBrainCouncil.decide`` runs a genuine two-brain deliberation: both brains
answer independently and concurrently, then the lead brain synthesises a final
verdict that is explicitly weighted toward its own view but must incorporate the
second brain's reasoning. This is exposed to the agent as the
``consult_dual_brain`` tool so it can put "everything important" to both brains.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from scrumbot.config import Settings, get_settings
from scrumbot.llm import get_llm

logger = logging.getLogger(__name__)


def build_council(settings: Optional[Settings] = None) -> Tuple[BaseChatModel, Optional[BaseChatModel]]:
    """Return ``(primary, secondary)`` chat models for the council.

    * ``primary`` is Nemotron when an NVIDIA key is configured, otherwise it
      transparently falls back to the Gemini model so the agent still runs.
    * ``secondary`` is Gemini. It is ``None`` only when the primary already *is*
      the secondary model (no NVIDIA key), because a brain cannot fall back to
      itself.
    """
    settings = settings or get_settings()

    primary_model = settings.primary_model
    secondary_model = settings.secondary_model

    # No NVIDIA key -> Nemotron is unreachable; run single-brain on Gemini.
    nemotron_available = bool(settings.nvidia_api_key) and "/" in primary_model
    if not nemotron_available:
        logger.warning(
            "NVIDIA key/model unavailable; dual-brain degrades to single-brain on %s.",
            secondary_model,
        )
        return get_llm(secondary_model, settings), None

    primary = get_llm(primary_model, settings)
    # If both slots resolve to the same model there is nothing to fall back to.
    if primary_model == secondary_model:
        return primary, None
    secondary = get_llm(secondary_model, settings)
    logger.info("Dual-brain council online: lead=%s, backup=%s", primary_model, secondary_model)
    return primary, secondary


@dataclass
class DualBrainCouncil:
    """A two-brain deliberation council used for high-stakes decisions."""

    primary: BaseChatModel
    secondary: Optional[BaseChatModel]
    primary_weight: float = 0.51
    secondary_weight: float = 0.49
    primary_name: str = "Nemotron"
    secondary_name: str = "Gemini"

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "DualBrainCouncil":
        settings = settings or get_settings()
        primary, secondary = build_council(settings)
        return cls(
            primary=primary,
            secondary=secondary,
            primary_weight=settings.primary_weight,
            secondary_weight=settings.secondary_weight,
        )

    @property
    def dual(self) -> bool:
        """True when two distinct brains are available to deliberate."""
        return self.secondary is not None

    async def _ask(self, brain: BaseChatModel, system: str, question: str) -> str:
        messages = [SystemMessage(content=system), HumanMessage(content=question)]
        try:
            resp = await brain.ainvoke(messages)
            return (resp.content or "").strip()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the caller
            logger.warning("Brain call failed: %s", exc)
            return f"(no answer — brain error: {exc})"

    async def decide(self, question: str, context: str = "") -> str:
        """Deliberate on ``question`` with both brains and return a final verdict.

        The two brains answer independently and concurrently; the lead brain then
        synthesises a decision weighted toward its own view (``primary_weight``)
        while explicitly accounting for the second brain's reasoning. When only
        one brain is available the single answer is returned directly.

        Every deliberation is persisted to the decision log so the council has a
        memory — the agent can recall past rulings with ``list_decisions`` and stay
        consistent instead of re-deciding from scratch. Persistence is best-effort
        (off the event loop) and never blocks or fails the decision itself.
        """
        base_context = (
            "You are a decision-making brain for LaunchPixel (launchpixel.in), an "
            "elite product/development agency. Be decisive, concrete and honest "
            "about trade-offs and risk."
        )
        if context:
            base_context += f"\n\nRelevant context:\n{context}"

        if not self.dual:
            verdict = await self._ask(self.primary, base_context, question)
            await self._record(question, verdict, "(no second brain configured)", verdict)
            return verdict

        lead_ans, second_ans = await asyncio.gather(
            self._ask(self.primary, f"{base_context}\n\nYou are the LEAD brain.", question),
            self._ask(self.secondary, f"{base_context}\n\nYou are the SECOND-OPINION brain.", question),
        )

        pct_lead = round(self.primary_weight * 100)
        pct_second = round(self.secondary_weight * 100)
        synthesis_prompt = (
            f"Decision to make:\n{question}\n\n"
            f"--- {self.primary_name} (lead, weight {pct_lead}%) said ---\n{lead_ans}\n\n"
            f"--- {self.secondary_name} (second opinion, weight {pct_second}%) said ---\n{second_ans}\n\n"
            "As the lead brain, deliver the FINAL decision. Weight your own view at "
            f"{pct_lead}% and the second opinion at {pct_second}%, but genuinely fold in "
            "anything the second brain raised that you missed. Respond with:\n"
            "1. **Decision:** one clear line.\n"
            "2. **Why:** 2-3 sentences.\n"
            "3. **Consensus:** state whether both brains agreed, or where they "
            "diverged and why you ruled the way you did.\n"
            "Keep it tight and use Discord markdown."
        )
        verdict = await self._ask(
            self.primary,
            f"{base_context}\n\nYou are the LEAD brain making the final call.",
            synthesis_prompt,
        )
        await self._record(question, lead_ans, second_ans, verdict)
        return verdict

    @staticmethod
    async def _record(question: str, lead_ans: str, second_ans: str, verdict: str) -> None:
        """Persist a deliberation to the decision log, best-effort and off-loop."""
        if not verdict:
            return
        try:
            from scrumbot.integrations import admin_db

            await asyncio.to_thread(
                admin_db.record_decision, question, lead_ans, second_ans, verdict
            )
        except Exception as exc:  # noqa: BLE001 - logging must never break a decision
            logger.warning("Failed to record decision: %s", exc)


def make_dual_brain_tool(council: DualBrainCouncil):
    """Build the ``consult_dual_brain`` LangChain tool bound to ``council``."""
    from langchain_core.tools import tool

    @tool
    async def consult_dual_brain(decision: str, context: str = "") -> str:
        """Put a high-stakes decision to BOTH AI brains (Nemotron lead + Gemini) and get a weighted verdict.

        Use this for anything important where a second opinion matters: whether to
        pursue a lead, how to handle a client escalation, pricing/scoping calls,
        prioritising the sprint, hiring, or any judgement where being wrong is
        costly. ``context`` is optional supporting information (board state, the
        lead's details, relevant SOPs). Returns the lead brain's final decision,
        the reasoning, and where the two brains agreed or diverged.
        """
        return await council.decide(decision, context)

    return consult_dual_brain
