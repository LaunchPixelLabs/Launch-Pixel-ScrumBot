"""Background schedulers for ScrumBot.

The daily standup posts the standup prompt to the configured channel
(``STANDUP_CHANNEL_ID``). With no channel configured it is a no-op, so the bot
runs fine out of the box.
"""
from __future__ import annotations

import datetime
import logging
import os

from discord.ext import commands, tasks
from google import genai

from scrumbot.config import get_settings
from scrumbot.prompts import STANDUP_PROMPT
from scrumbot.integrations import admin_db

logger = logging.getLogger(__name__)


class ScrumScheduler(commands.Cog):
    """Cog managing scheduled jobs."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._channel_id = get_settings().standup_channel_id
        self.gemini_client = None
        
        # We try to use Gemini/Nemotron if available for the sassy nagging
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
        if GEMINI_API_KEY and GEMINI_API_KEY != 'your_gemini_api_key_here':
            try:
                self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            except Exception as e:
                logger.error(f'Failed to initialize Gemini: {e}')
                
        self.daily_standup.start()
        self.nag_lazy_members.start()

    def cog_unload(self) -> None:
        self.daily_standup.cancel()
        self.nag_lazy_members.cancel()

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
        active_tickets = admin_db.get_active_tickets()
        if not active_tickets:
            return
            
        stale_tickets = []
        for t in active_tickets:
            # Basic stale logic: If status is Pending or Active and it has no assignee or is old
            stale_tickets.append(f"Ticket {t['id']}: {t['title']} | Status: {t['status']} | Assignee: {t.get('assignee_name', 'Unassigned')}")
            
        if not stale_tickets:
            return
            
        nag_prompt = (
            "You are a strict, sassy, no-nonsense AI Scrum Master for the agency 'Launch Pixel'. "
            "You are reviewing the following delayed or active tickets in our Neon DB:\n" + 
            "\n".join(stale_tickets) + 
            "\n\nWrite a 3-4 sentence message calling out the team to update these tickets. "
            "If any ticket is unassigned, tell an intern to pick it up. "
            "If a ticket is extremely delayed, escalate it by mentioning the CEO (Vivek). "
            "Be direct and use professional sass."
        )
        
        message = "⚠️ **Scrum Master Alert:** Please review the active tasks on the Kanban board. Some tasks are lingering!"
        if self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=nag_prompt
                )
                message = f"🚨 **AI Scrum Master Daily Nag:**\n{response.text}"
            except Exception as e:
                logger.error(f"Failed to generate nag message: {e}")

        # Post to the standup channel or a general alerts channel
        if self._channel_id:
            channel = self.bot.get_channel(self._channel_id)
            if channel:
                await channel.send(message)

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
