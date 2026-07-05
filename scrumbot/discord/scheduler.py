"""Background schedulers for ScrumBot.

The daily standup posts the standup prompt to the configured channel
(``STANDUP_CHANNEL_ID``). With no channel configured it is a no-op, so the bot
runs fine out of the box.
"""
from __future__ import annotations

import datetime
import logging

from discord.ext import commands, tasks
from google import genai

from scrumbot.config import get_settings
from scrumbot.prompts import STANDUP_PROMPT
from scrumbot.integrations import admin_db

logger = logging.getLogger(__name__)

# A ticket with no activity for this long is considered "stale" and gets nagged.
_STALE_AFTER = datetime.timedelta(hours=48)


class ScrumScheduler(commands.Cog):
    """Cog managing scheduled jobs (daily standup, stale-ticket nagging, lead polling)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        settings = get_settings()
        self._channel_id = settings.standup_channel_id
        self._gemini_model = settings.gemini_model
        self._composio_enabled = bool(
            settings.composio_api_key and settings.composio_user_id and settings.composio_toolkits
        )
        self.gemini_client = None

        # Gemini is the "second brain" used for the sassy nag copy.
        api_key = settings.gemini_api_key
        if api_key and api_key != 'your_gemini_api_key_here':
            try:
                self.gemini_client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.error(f'Failed to initialize Gemini: {e}')

        self.daily_standup.start()
        self.nag_lazy_members.start()
        # Lead polling depends on Composio Gmail tools; only run it when wired up
        # so we don't burn NIM/agent calls every 2 hours for nothing.
        if self._composio_enabled:
            self.poll_leads.start()

    def cog_unload(self) -> None:
        self.daily_standup.cancel()
        self.nag_lazy_members.cancel()
        if self.poll_leads.is_running():
            self.poll_leads.cancel()

    async def _gemini(self, prompt: str) -> str:
        """Async single-shot Gemini generation (never blocks the event loop)."""
        response = await self.gemini_client.aio.models.generate_content(
            model=self._gemini_model, contents=prompt
        )
        return (response.text or "").strip()

    # 09:00 UTC every day.
    _run_at = datetime.time(hour=9, minute=0, tzinfo=datetime.timezone.utc)

    @tasks.loop(time=_run_at)
    async def daily_standup(self) -> None:
        logger.info("Running daily standup...")
        if not self._channel_id:
            return
        channel = self.bot.get_channel(self._channel_id)
        if channel is None:
            logger.warning("Standup channel %s not found or not cached.", self._channel_id)
            return
        await channel.send(STANDUP_PROMPT)

    @daily_standup.before_loop
    async def before_standup(self) -> None:
        await self.bot.wait_until_ready()

    # Run nagging every 24 hours at 12:00 UTC
    _nag_time = datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc)
    
    @tasks.loop(time=_nag_time)
    async def nag_lazy_members(self) -> None:
        logger.info("Running nagging check...")
        if not self._channel_id:
            return
        channel = self.bot.get_channel(self._channel_id)
        if channel is None:
            logger.warning("Nag channel %s not found or not cached.", self._channel_id)
            return

        active_tickets = admin_db.get_active_tickets()
        if not active_tickets:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        stale_tickets = []
        for t in self._sorted_by_staleness(active_tickets):
            if self._is_stale(t, now):
                stale_tickets.append(
                    f"Ticket {t['id']}: {t['title']} | Status: {t['status']} | "
                    f"Assignee: {t.get('assignee_name', 'Unassigned')}"
                )

        if not stale_tickets:
            logger.info("No stale tickets to nag about.")
            return

        nag_prompt = (
            "You are a strict, sassy, no-nonsense AI Scrum Master for the agency 'Launch Pixel'. "
            "These tickets have had no update in over 48 hours:\n"
            + "\n".join(stale_tickets)
            + "\n\nWrite a 3-4 sentence message calling out the team to update these tickets. "
            "If any ticket is unassigned, tell an intern to pick it up. "
            "If a ticket is extremely delayed, escalate it by mentioning the CEO (Vivek). "
            "Be direct and use professional sass."
        )

        message = (
            "⚠️ **Scrum Master Alert:** These tasks have gone quiet for 48h+:\n"
            + "\n".join(f"• {line}" for line in stale_tickets)
        )
        if self.gemini_client:
            try:
                message = f"🚨 **AI Scrum Master Daily Nag:**\n{await self._gemini(nag_prompt)}"
            except Exception as e:
                logger.error(f"Failed to generate nag message: {e}")

        await channel.send(message)

    @staticmethod
    def _is_stale(ticket: dict, now: datetime.datetime) -> bool:
        """A ticket is stale if it hasn't been updated within ``_STALE_AFTER``.

        Tickets with no known ``updated_at`` are treated as stale (better to
        over-remind than to silently drop them).
        """
        updated = ticket.get("updated_at")
        if updated is None:
            return True
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=datetime.timezone.utc)
        return (now - updated) >= _STALE_AFTER

    @staticmethod
    def _sorted_by_staleness(tickets: list) -> list:
        """Oldest-updated first, so the nag leads with the most-neglected tickets."""
        return sorted(
            tickets,
            key=lambda t: t.get("updated_at") or datetime.datetime.min.replace(
                tzinfo=datetime.timezone.utc
            ),
        )

    @nag_lazy_members.before_loop
    async def before_nag(self) -> None:
        await self.bot.wait_until_ready()

    # Lead polling every 2 hours
    @tasks.loop(hours=2)
    async def poll_leads(self) -> None:
        logger.info("Polling Gmail for leads via Composio...")
        if not self._channel_id:
            return
            
        try:
            # Get the app and agent from the cog's bot if we attached it
            app = getattr(self.bot, "app", None)
            if not app or not app.agent:
                return
                
            prompt = (
                "Use your Composio GMAIL tools to search for recent emails (last 24 hours) "
                "that look like new business leads or inquiries. If you find any:\n"
                "1. Summarize the lead (Who, what they want).\n"
                "2. Draft a professional, conversion-focused response.\n"
                "3. Return the summary and the drafted response in your final answer.\n"
                "If no new leads are found, return 'NO_LEADS'."
            )
            
            response = await app.agent.ask(prompt, thread_id="lead_polling_thread")
            
            if "NO_LEADS" not in response and len(response.strip()) > 20:
                channel = self.bot.get_channel(self._channel_id)
                if channel:
                    msg = f"📩 **New Lead Detected!**\n\n{response}"
                    # Truncate if discord limits (2000 chars)
                    if len(msg) > 1900:
                        msg = msg[:1900] + "...[truncated]"
                    await channel.send(msg)
                    
        except Exception as e:
            logger.error(f"Error polling leads: {e}")

    @poll_leads.before_loop
    async def before_poll(self) -> None:
        await self.bot.wait_until_ready()


async def setup_scheduler(bot: commands.Bot) -> None:
    """Add the scheduler cog to ``bot``."""
    await bot.add_cog(ScrumScheduler(bot))
