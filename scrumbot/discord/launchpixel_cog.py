"""Launch Pixel enterprise Discord cog.

Prefix (``!``) commands for the human-facing DevOps workflow: server
automation, onboarding, a JIRA-style ticketing system backed by Neon Postgres,
daily standups, and an AI "Scrum Master" blocker helper.

Architecture note: the LangGraph agent (NVIDIA NIM / Nemotron) is the *core
brain* and powers the slash commands in :mod:`scrumbot.discord.bot`. Gemini is
the *second brain* used here for quick, single-shot generations (blocker
advice, nudges). All Gemini calls go through :meth:`LaunchPixelCog._gemini`
which uses the async client so the Discord gateway is never blocked.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import discord
from discord.ext import commands
from google import genai

from scrumbot.config import get_settings
from scrumbot.integrations import admin_db as db
from scrumbot.discord.views import TaskView

logger = logging.getLogger(__name__)


class OnboardingView(discord.ui.View):
    """Persistent role-selection panel posted in ``#onboarding-portal``."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _assign_role(
        self,
        interaction: discord.Interaction,
        role_name: str,
        color: discord.Color,
        counterpart_name: str,
        success_msg: str,
        already_msg: str,
    ) -> None:
        """Grant ``role_name`` (creating it if needed) and drop the counterpart role."""
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try:
                role = await guild.create_role(
                    name=role_name, color=color, hoist=True, mentionable=True
                )
            except discord.errors.Forbidden:
                await interaction.response.send_message(
                    "⚠️ **Administrative Warning:** The bot lacks permissions to create "
                    "roles. Please drag the `LP_Bot` role to the top of the Role "
                    "Hierarchy in Server Settings.",
                    ephemeral=True,
                )
                return

        try:
            if role in interaction.user.roles:
                await interaction.response.send_message(already_msg, ephemeral=True)
                return
            counterpart = discord.utils.get(guild.roles, name=counterpart_name)
            if counterpart and counterpart in interaction.user.roles:
                await interaction.user.remove_roles(counterpart)
            await interaction.user.add_roles(role)
            await interaction.response.send_message(success_msg, ephemeral=True)
        except discord.errors.Forbidden:
            await interaction.response.send_message(
                "⚠️ **Administrative Warning:** The bot lacks permissions to assign this "
                "role. Please drag the `LP_Bot` role to the top of the Role Hierarchy in "
                "Server Settings.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="Core Associate",
        style=discord.ButtonStyle.blurple,
        custom_id="onboarding_core_associate",
    )
    async def button_core(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._assign_role(
            interaction,
            role_name="Core Associate",
            color=discord.Color.blue(),
            counterpart_name="Junior Associate",
            success_msg="💼 Access Granted: You have been assigned the **Core Associate** credentials.",
            already_msg="💼 You already possess the **Core Associate** credential.",
        )

    @discord.ui.button(
        label="Junior Associate",
        style=discord.ButtonStyle.success,
        custom_id="onboarding_junior_associate",
    )
    async def button_junior(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._assign_role(
            interaction,
            role_name="Junior Associate",
            color=discord.Color.green(),
            counterpart_name="Core Associate",
            success_msg="🌱 Access Granted: You have been assigned the **Junior Associate** (Internship) credentials.",
            already_msg="🌱 You already possess the **Junior Associate** credential.",
        )


class LaunchPixelCog(commands.Cog):
    """Human-facing ``!`` command surface for the Launch Pixel workspace."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.gemini_client: genai.Client | None = None
        self.gemini_model = get_settings().gemini_model

        api_key = get_settings().gemini_api_key
        if api_key and api_key != "your_gemini_api_key_here":
            try:
                self.gemini_client = genai.Client(api_key=api_key)
            except Exception as exc:  # noqa: BLE001 - degrade gracefully
                logger.error("Failed to initialize Gemini: %s", exc)

    async def cog_load(self) -> None:
        """Register the persistent onboarding view once when the cog is added."""
        self.bot.add_view(OnboardingView())
        logger.info("Persistent Onboarding View registered.")

    async def _gemini(self, prompt: str) -> str:
        """Run a single-shot Gemini generation off the gateway loop.

        Uses the async client (``client.aio``) so a slow model call never blocks
        Discord's heartbeat. Raises if Gemini is not configured; callers guard on
        ``self.gemini_client``.
        """
        response = await self.gemini_client.aio.models.generate_content(
            model=self.gemini_model, contents=prompt
        )
        return (response.text or "").strip()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("%s is connected and ready to Scrum!", self.bot.user)
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Launch Pixel tickets | !help",
            )
        )

    # ================= SERVER AUTOMATION SETUP =================

    @commands.command(name="setup_server")
    @commands.has_permissions(administrator=True)
    async def setup_server(self, ctx: commands.Context) -> None:
        """Automate Launch Pixel server layout, channels, and role hierarchy."""
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a server!")
            return

        progress_msg = await ctx.send("⚡ **Initializing Launch Pixel Server Automation...**")

        # 1. Roles
        await progress_msg.edit(content="⚡ **Creating Role Hierarchy...** ⏳")
        roles_config = [
            {"name": "👑 Founder / CEO", "color": 0xD4AF37},
            {"name": "📋 Product Manager (Scrum Master)", "color": 0x9B5DE5},
            {"name": "💻 Senior Dev", "color": 0x00F5D4},
            {"name": "🎨 UI/UX Designer", "color": 0xF15BB5},
            {"name": "🧪 QA Tester", "color": 0x2ECC71},
        ]
        for rc in roles_config:
            role = discord.utils.get(ctx.guild.roles, name=rc["name"])
            if not role:
                await ctx.guild.create_role(
                    name=rc["name"],
                    color=discord.Color(rc["color"]),
                    hoist=True,
                    mentionable=True,
                )

        # 2. Categories & channels
        await progress_msg.edit(content="⚡ **Setting up Categories & Channels...** ⏳")
        categories = {
            "EXECUTIVE OVERSIGHT": [
                {"name": "exec-boardroom", "type": "text"},
                {"name": "enterprise-kpis", "type": "text"},
                {"name": "Boardroom Sync", "type": "voice"},
            ],
            "PROGRAM OPERATIONS": [
                {"name": "ticket-activity-feed", "type": "text"},
            ],
            "INTEGRATED COMMUNICATIONS": [
                {"name": "whatsapp-client-sync", "type": "text"},
                {"name": "external-email-tickets", "type": "text"},
                {"name": "incident-alerts", "type": "text"},
                {"name": "blocker-resolution", "type": "text"},
            ],
            "ENGINEERING & TECHNOLOGY": [
                {"name": "eng-governance", "type": "text"},
                {"name": "eng-sprint-backlog", "type": "text"},
                {"name": "Eng Architecture Sync", "type": "voice"},
                {"name": "Eng Daily Standup", "type": "voice"},
            ],
            "OPERATIONS & LOGISTICS": [
                {"name": "ops-governance", "type": "text"},
                {"name": "ops-sprint-backlog", "type": "text"},
                {"name": "Ops Operations Sync", "type": "voice"},
            ],
            "MARKETING & GROWTH": [
                {"name": "mkt-campaign-tracking", "type": "text"},
                {"name": "mkt-sprint-backlog", "type": "text"},
                {"name": "Mkt Campaign Sync", "type": "voice"},
            ],
            "FINANCE & TREASURY": [
                {"name": "fin-treasury-compliance", "type": "text"},
                {"name": "fin-invoice-tracking", "type": "text"},
                {"name": "Fin Treasury Review", "type": "voice"},
            ],
            "ONBOARDING": [
                {"name": "onboarding-portal", "type": "text"},
            ],
            "ACTIVE WORKSPACES": [],
            "ARCHIVED WORKSPACES": [],
        }

        forum_error_msg = ""
        for cat_name, channels in categories.items():
            category = discord.utils.get(ctx.guild.categories, name=cat_name)
            if not category:
                category = await ctx.guild.create_category(name=cat_name)

            for ch in channels:
                ch_name, ch_type = ch["name"], ch["type"]
                if ch_type == "text":
                    existing = discord.utils.find(
                        lambda c: c.name.lower() == ch_name.lower()
                        and c.category == category
                        and isinstance(c, discord.TextChannel),
                        ctx.guild.channels,
                    )
                    if not existing:
                        await ctx.guild.create_text_channel(name=ch_name, category=category)
                elif ch_type == "voice":
                    existing = discord.utils.find(
                        lambda c: c.name.lower() == ch_name.lower()
                        and c.category == category
                        and isinstance(c, discord.VoiceChannel),
                        ctx.guild.channels,
                    )
                    if not existing:
                        await ctx.guild.create_voice_channel(name=ch_name, category=category)

            # Kanban forum lives inside PROGRAM OPERATIONS.
            if cat_name == "PROGRAM OPERATIONS":
                forum_ch = discord.utils.find(
                    lambda c: c.name.lower() == "kanban-board" and c.category == category,
                    ctx.guild.channels,
                )
                if not forum_ch:
                    tags = [
                        discord.ForumTag(name="New", emoji="🆕"),
                        discord.ForumTag(name="Planned", emoji="📅"),
                        discord.ForumTag(name="Refining", emoji="🔧"),
                        discord.ForumTag(name="Active", emoji="▶️"),
                        discord.ForumTag(name="Reviewing", emoji="👀"),
                        discord.ForumTag(name="Blocked", emoji="⛔"),
                        discord.ForumTag(name="Closed", emoji="📁"),
                    ]
                    try:
                        await ctx.guild.create_forum(
                            name="kanban-board",
                            category=category,
                            available_tags=tags,
                            topic="Project Kanban Board - Create tasks using !ticket create!",
                        )
                    except discord.errors.HTTPException as exc:
                        if exc.code == 40041:
                            forum_error_msg = (
                                "\n⚠️ *Note: Could not create forum '#kanban-board' because "
                                "**Community Features** are not enabled in Server Settings.*"
                            )
                        else:
                            forum_error_msg = f"\n⚠️ *Forum creation failed: {exc.text}*"

        success_embed = discord.Embed(
            title="🎉 Launch Pixel Server Setup Complete!",
            description="I have automatically set up your roles, operational text rooms, and voice channels.",
            color=0xD4AF37,
        )
        success_embed.add_field(
            name="Hierarchy Roles",
            value="\n".join(f"🔹 {rc['name']}" for rc in roles_config),
            inline=True,
        )
        success_embed.add_field(
            name="Operations Channels",
            value="✅ Info & Stats\n✅ Workspace & Chats\n✅ Dev / Design / QA Rooms\n✅ Custom Voice Channels\n✅ DevOps & Alerts",
            inline=True,
        )
        if forum_error_msg:
            success_embed.add_field(name="Kanban Forum Status", value=forum_error_msg, inline=False)
        else:
            success_embed.add_field(
                name="Kanban Forum Status",
                value="📋 `#kanban-board` created with New, Planned, Refining, Active, Reviewing, Blocked, and Closed tags!",
                inline=False,
            )

        await progress_msg.delete()
        await ctx.send(embed=success_embed)

    @commands.command(name="setup_onboarding")
    @commands.has_permissions(administrator=True)
    async def setup_onboarding(self, ctx: commands.Context) -> None:
        """Deploy the onboarding verification panel into ``#onboarding-portal``."""
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a server!")
            return

        channel = discord.utils.find(
            lambda c: c.name.lower() == "onboarding-portal", ctx.guild.text_channels
        )
        if not channel:
            await ctx.send(
                "❌ Could not find `#onboarding-portal`! Please run `!setup_server` first."
            )
            return

        try:
            await channel.purge(limit=100)
        except (discord.errors.Forbidden, discord.errors.HTTPException) as exc:
            logger.warning("Could not purge onboarding channel: %s", exc)

        embed = discord.Embed(
            title="🏢 LAUNCH PIXEL • ENTERPRISE ONBOARDING PORTAL",
            description=(
                "Welcome to the **Launch Pixel Core Operations Workspace**. To initiate your "
                "corporate onboarding and secure access to your designated tracking channels, "
                "please verify your credentials below:\n\n"
                "**💼 CORE ASSOCIATE (Regular Staff)**\n"
                "Select this option if you are a full-time partner, director, engineer, "
                "marketer, or operational manager.\n\n"
                "**🌱 JUNIOR ASSOCIATE (Internship Program)**\n"
                "Select this option if you are currently enrolled in our professional "
                "internship program."
            ),
            color=0xD4AF37,
        )
        embed.set_footer(text="Launch Pixel Security & Credentials System • Select to Assign Role")
        await channel.send(embed=embed, view=OnboardingView())
        await ctx.send(f"✅ Onboarding verification panel deployed inside {channel.mention}!")

    # ================= JIRA TICKETING SYSTEM =================

    @commands.group(name="ticket", invoke_without_command=True)
    async def ticket_group(self, ctx: commands.Context) -> None:
        """JIRA-style ticket operations backed by Neon PostgreSQL."""
        embed = discord.Embed(
            title="🎫 Launch Pixel DevOps Bot",
            description="JIRA/Azure DevOps task management integrated with serverless Neon Postgres.",
            color=0x9B5DE5,
        )
        embed.add_field(
            name="🆕 Create Ticket",
            value="`!ticket create <Title> | <Description> | [Assignee] | [Priority] | [Story Points] | [Days] | [Start] | [End] | [Acceptance]`",
            inline=False,
        )
        embed.add_field(name="👤 Assign Member", value="`!ticket assign <LP-X> <@Member>`", inline=False)
        embed.add_field(
            name="▶️ Update Status",
            value="`!ticket status <LP-X> <New|Planned|Refining|Active|Reviewing|Blocked|Closed>`",
            inline=False,
        )
        embed.add_field(name="📋 List Tickets", value="`!ticket list`", inline=False)
        embed.add_field(name="🔍 View Details & Comments", value="`!ticket view <LP-X>`", inline=False)
        await ctx.send(embed=embed)

    @ticket_group.command(name="create")
    async def ticket_create(self, ctx: commands.Context, *, args: str) -> None:
        """Create a ticket in Postgres, update the Kanban Board, and spin up a channel."""
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a server!")
            return

        parts = [p.strip() for p in args.split("|")]
        if len(parts) < 2:
            await ctx.send(
                "❌ Syntax error! Use: `!ticket create Title | Description | [Assignee] | "
                "[Priority] | [Story Points] | [Days] | [Start Date] | [End Date] | "
                "[Acceptance Criteria]`"
            )
            return

        title = parts[0]
        description = parts[1]
        assignee_raw = parts[2] if len(parts) > 2 and parts[2] else "Unassigned"
        priority = parts[3] if len(parts) > 3 and parts[3] else "Medium"
        story_points = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1
        priority_days = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 5
        start_date_str = parts[6] if len(parts) > 6 and parts[6] else datetime.now().strftime("%Y-%m-%d")
        end_date_str = parts[7] if len(parts) > 7 and parts[7] else datetime.now().strftime("%Y-%m-%d")
        acceptance_criteria = (
            parts[8] if len(parts) > 8 and parts[8] else "No specific acceptance criteria specified."
        )

        # Resolve a mentioned assignee if present.
        assignee_member = None
        if assignee_raw.startswith("<@") and assignee_raw.endswith(">"):
            try:
                member_id = int(assignee_raw.strip("<@!>"))
                assignee_member = ctx.guild.get_member(member_id)
                if not assignee_member:
                    try:
                        assignee_member = await ctx.guild.fetch_member(member_id)
                    except discord.errors.HTTPException:
                        pass
            except ValueError:
                pass

        next_num = db.get_last_ticket_id() + 1
        ticket_id = f"LP-{next_num}"

        # 1. Dedicated workspace channel.
        ticket_category = discord.utils.get(ctx.guild.categories, name="ACTIVE WORKSPACES")
        if not ticket_category:
            ticket_category = await ctx.guild.create_category(name="ACTIVE WORKSPACES")

        clean_title = "".join(c if c.isalnum() else "-" for c in title.lower())
        clean_title = clean_title.replace("--", "-").strip("-")
        channel_name = f"lp-ticket-{next_num}-{clean_title}"[:100]
        topic_str = (
            f"{ticket_id}: {title} | Assignee: "
            f"{assignee_member.display_name if assignee_member else assignee_raw} | "
            f"SP: {story_points} | Priority: {priority}"
        )
        ticket_channel = await ctx.guild.create_text_channel(
            name=channel_name, category=ticket_category, topic=topic_str
        )

        # 2. Kanban forum card.
        forum_channel = discord.utils.find(
            lambda c: c.name.lower() == "kanban-board", ctx.guild.forums
        )
        thread_id = None
        if forum_channel:
            new_tag = discord.utils.find(
                lambda t: t.name.lower() == "new", forum_channel.available_tags
            )
            applied_tags = [new_tag] if new_tag else []
            forum_content = (
                f"**Ticket ID:** `{ticket_id}`\n"
                f"**Priority:** `{priority}` ({priority_days} days estimate)\n"
                f"**Story Points:** `{story_points} SP`\n"
                f"**Dates:** `{start_date_str}` to `{end_date_str}`\n"
                f"**Assignee:** {assignee_raw}\n"
                f"**Workspace Channel:** {ticket_channel.mention}\n\n"
                f"**Description:**\n{description}\n\n"
                f"**Acceptance Criteria:**\n{acceptance_criteria}"
            )
            try:
                thread_with_msg = await forum_channel.create_thread(
                    name=f"[{ticket_id}] {title}",
                    content=forum_content,
                    applied_tags=applied_tags,
                )
                thread_id = thread_with_msg.thread.id
            except Exception as exc:  # noqa: BLE001 - forum is optional
                logger.warning("Failed to post to Kanban Forum: %s", exc)

        # 3. Persist to Neon.
        db.create_ticket(
            ticket_id=ticket_id,
            title=title,
            description=description,
            assignee_id=assignee_member.id if assignee_member else None,
            assignee_name=assignee_member.display_name if assignee_member else assignee_raw,
            priority=priority,
            priority_days=priority_days,
            start_date=start_date_str,
            end_date=end_date_str,
            story_points=story_points,
            acceptance_criteria=acceptance_criteria,
            thread_id=thread_id,
            channel_id=ticket_channel.id,
        )

        # 4. Notify.
        embed = discord.Embed(
            title=f"🆕 Ticket Created: {ticket_id}",
            description=f"**Title:** {title}\n**Story Points:** {story_points} SP\n**Assignee:** {assignee_raw}",
            color=0x2ECC71,
        )
        embed.add_field(name="Discussion Channel", value=ticket_channel.mention, inline=True)
        if thread_id:
            embed.add_field(
                name="Kanban Board Card",
                value=f"[Go to Card](https://discord.com/channels/{ctx.guild.id}/{forum_channel.id}/{thread_id})",
                inline=True,
            )
        await ctx.send(embed=embed)

        welcome_embed = discord.Embed(
            title=f"🎫 {ticket_id} - Task Workspace",
            description=(
                f"This channel is dedicated to the discussion and execution of: **{title}**.\n\n"
                f"**Goal Description:**\n{description}"
            ),
            color=0x9B5DE5,
        )
        welcome_embed.add_field(name="Story Points", value=f"{story_points} SP", inline=True)
        welcome_embed.add_field(name="Assignee", value=assignee_raw, inline=True)
        welcome_embed.add_field(name="Priority (Days)", value=f"{priority} ({priority_days} days)", inline=True)
        welcome_embed.add_field(name="Timelines", value=f"📅 {start_date_str} to {end_date_str}", inline=False)
        welcome_embed.add_field(name="Acceptance Criteria", value=acceptance_criteria, inline=False)
        welcome_embed.set_footer(
            text="Messages and files posted here are logged to the Neon database."
        )
        await ticket_channel.send(embed=welcome_embed)

        await self._log_activity(
            ctx.guild,
            f"🆕 **{ctx.author.name}** created ticket **{ticket_id}**: *{title}* "
            f"(SP: {story_points}, Assigned to: {assignee_raw})",
        )

    @ticket_group.command(name="assign")
    async def ticket_assign(
        self, ctx: commands.Context, ticket_id: str, member: discord.Member
    ) -> None:
        """Assign an existing ticket to a team member."""
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a server!")
            return

        ticket_id = ticket_id.upper()
        t = db.get_ticket(ticket_id)
        if not t:
            await ctx.send(f"❌ Ticket `{ticket_id}` not found!")
            return

        db.update_ticket_assignee(ticket_id, member.id, member.display_name)

        channel = ctx.guild.get_channel(t["channel_id"]) if t.get("channel_id") else None
        if channel:
            await channel.edit(
                topic=f"{t['id']}: {t['title']} | Assignee: {member.display_name} | SP: {t['story_points']}"
            )
            await channel.send(
                f"👤 **{member.mention}** has been assigned to this ticket by {ctx.author.name}!"
            )

        forum_channel = discord.utils.find(
            lambda c: c.name.lower() == "kanban-board", ctx.guild.forums
        )
        if forum_channel and t.get("thread_id"):
            try:
                thread = ctx.guild.get_thread(t["thread_id"])
                if thread:
                    content = (
                        f"**Ticket ID:** `{t['id']}`\n"
                        f"**Priority:** `{t['priority']}` ({t['priority_days']} days estimate)\n"
                        f"**Story Points:** `{t['story_points']} SP`\n"
                        f"**Dates:** `{t['start_date']}` to `{t['end_date']}`\n"
                        f"**Assignee:** {member.mention}\n"
                        f"**Workspace Channel:** {channel.mention if channel else 'None'}\n\n"
                        f"**Description:**\n{t['description']}\n\n"
                        f"**Acceptance Criteria:**\n{t['acceptance_criteria']}"
                    )
                    await thread.edit(content=content)
            except Exception as exc:  # noqa: BLE001 - forum is optional
                logger.warning("Failed to update forum thread details: %s", exc)

        await ctx.send(f"✅ Ticket **{ticket_id}** has been assigned to **{member.display_name}**.")
        await self._log_activity(
            ctx.guild,
            f"👤 **{ctx.author.name}** assigned **{ticket_id}** to **{member.display_name}**",
        )

    @ticket_group.command(name="status")
    async def ticket_status(self, ctx: commands.Context, ticket_id: str, status: str) -> None:
        """Update status, move the Kanban card, and auto-archive completed rooms."""
        if not ctx.guild:
            await ctx.send("❌ This command must be used in a server!")
            return

        ticket_id = ticket_id.upper()
        status = status.capitalize()
        valid_statuses = ["New", "Planned", "Refining", "Active", "Reviewing", "Blocked", "Closed"]
        if status not in valid_statuses:
            await ctx.send(
                "❌ Invalid status! Choose from: `New`, `Planned`, `Refining`, `Active`, "
                "`Reviewing`, `Blocked`, `Closed`"
            )
            return

        t = db.get_ticket(ticket_id)
        if not t:
            await ctx.send(f"❌ Ticket `{ticket_id}` not found!")
            return

        old_status = t["status"]
        db.update_ticket_status(ticket_id, status)

        forum_channel = discord.utils.find(
            lambda c: c.name.lower() == "kanban-board", ctx.guild.forums
        )
        if forum_channel and t.get("thread_id"):
            try:
                thread = ctx.guild.get_thread(t["thread_id"])
                if thread:
                    new_tag = discord.utils.find(
                        lambda tag: tag.name.lower() == status.lower(),
                        forum_channel.available_tags,
                    )
                    applied_tags = [new_tag] if new_tag else []
                    await thread.edit(applied_tags=applied_tags)
            except Exception as exc:  # noqa: BLE001 - forum is optional
                logger.warning("Failed to update forum tag: %s", exc)

        channel = ctx.guild.get_channel(t["channel_id"]) if t.get("channel_id") else None
        if channel:
            await channel.send(
                f"🔄 Status changed: **{old_status}** ➡️ **{status}** (updated by {ctx.author.name})"
            )

        if status == "Closed" and channel:
            archive_category = discord.utils.find(
                lambda c: c.name.lower() == "archived workspaces", ctx.guild.categories
            )
            if not archive_category:
                archive_category = await ctx.guild.create_category(name="ARCHIVED WORKSPACES")

            await channel.send(
                f"📁 **Notice:** This ticket is now **{status}**. Moving to archived channels "
                "and locking in 5 seconds..."
            )
            await asyncio.sleep(5)
            try:
                await channel.edit(category=archive_category)
                overwrite = channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = False
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
                await channel.send("🔒 *This workspace is now archived and read-only.*")
            except Exception as exc:  # noqa: BLE001 - report to user
                await channel.send(f"⚠️ Failed to complete archiving permissions: {exc}")

        await ctx.send(f"✅ Ticket **{ticket_id}** status updated to **{status}**.")
        await self._log_activity(
            ctx.guild,
            f"🔄 **{ctx.author.name}** updated status of **{ticket_id}** to **{status}**",
        )

    @ticket_group.command(name="list")
    async def ticket_list(self, ctx: commands.Context) -> None:
        """List all active (non-closed) tickets from Neon."""
        active_tickets = db.get_active_tickets()
        if not active_tickets:
            await ctx.send("📋 There are currently no active tickets! Use `!ticket create` to get started.")
            return

        embed = discord.Embed(
            title="📋 Launch Pixel - Active Tickets Board",
            description="Currently active tasks loaded from Neon serverless Postgres:",
            color=0xD4AF37,
        )
        for t in active_tickets:
            channel_mention = f"<#{t['channel_id']}>" if t.get("channel_id") else "No channel"
            end_date = t.get("end_date")
            end_date_fmt = end_date.strftime("%Y-%m-%d") if end_date else "Not set"
            embed.add_field(
                name=f"[{t['id']}] {t['title']}",
                value=(
                    f"👤 **Assignee:** {t['assignee_name']} | 🚀 **Points:** `{t['story_points']} SP`\n"
                    f"⚡ **Priority:** {t['priority']} ({t['priority_days']} days) | 🔄 **Status:** `{t['status']}`\n"
                    f"📅 **Due Date:** {end_date_fmt} | 💬 Workspace: {channel_mention}"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @ticket_group.command(name="view")
    async def ticket_view(self, ctx: commands.Context, ticket_id: str) -> None:
        """Show a detailed ticket sheet with comments and attachments."""
        ticket_id = ticket_id.upper()
        t = db.get_ticket(ticket_id)
        if not t:
            await ctx.send(f"❌ Ticket `{ticket_id}` not found in Neon database!")
            return

        colors = {"high": 0xE74C3C, "medium": 0xF39C12, "low": 0x3498DB}
        color = colors.get(t["priority"].lower(), 0x9B5DE5)

        embed = discord.Embed(
            title=f"🎫 {t['id']}: {t['title']}",
            description=t["description"] or "*No description provided*",
            color=color,
        )
        embed.add_field(name="👤 Assignee", value=t["assignee_name"], inline=True)
        embed.add_field(name="🚀 Story Points", value=f"{t['story_points']} SP", inline=True)
        embed.add_field(name="🔄 Status", value=f"`{t['status']}`", inline=True)
        embed.add_field(name="⚡ Priority", value=f"{t['priority']} ({t['priority_days']} days)", inline=True)
        start_fmt = t["start_date"].strftime("%Y-%m-%d") if t.get("start_date") else "Not set"
        end_fmt = t["end_date"].strftime("%Y-%m-%d") if t.get("end_date") else "Not set"
        embed.add_field(name="📅 Timelines", value=f"{start_fmt} to {end_fmt}", inline=True)
        channel_mention = f"<#{t['channel_id']}>" if t.get("channel_id") else "None"
        embed.add_field(name="💬 Workspace Channel", value=channel_mention, inline=True)
        embed.add_field(
            name="📝 Acceptance Criteria",
            value=t["acceptance_criteria"] or "*None specified*",
            inline=False,
        )

        attachments = db.get_ticket_attachments(ticket_id)
        if attachments:
            attach_text = "".join(f"📂 [{a['file_name']}]({a['file_url']})\n" for a in attachments)
            embed.add_field(name="📎 Attachments, Files & Links", value=attach_text, inline=False)

        comments = db.get_ticket_comments(ticket_id)
        if comments:
            comment_text = ""
            for c in comments[-5:]:
                date_str = c["created_at"].strftime("%m-%d %H:%M")
                comment_text += f"💬 **{c['author_name']}** ({date_str}): {c['comment_text']}\n"
            embed.add_field(name="💬 Recent Workspace Updates", value=comment_text, inline=False)

        forum_channel = discord.utils.find(
            lambda c: c.name.lower() == "kanban-board", ctx.guild.forums
        )
        if forum_channel and t.get("thread_id"):
            embed.add_field(
                name="📋 Kanban Card",
                value=f"[Go to Card](https://discord.com/channels/{ctx.guild.id}/{forum_channel.id}/{t['thread_id']})",
                inline=True,
            )

        embed.set_footer(text="Task logged in Neon Postgres Serverless DB")
        view = TaskView(ticket_id=ticket_id, callback_func=self._handle_ticket_action)
        await ctx.send(embed=embed, view=view)

    # ================= STANDUP & AI BLOCKER RESOLUTION =================

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        """Premium custom help command for the Launch Pixel DevOps Bot."""
        embed = discord.Embed(
            title="🤖 Launch Pixel DevOps Bot - Help Guide",
            description="Your complete manual for the Launch Pixel automated server & DevOps tracking system.",
            color=0xD4AF37,
        )
        embed.add_field(
            name="⚡ Server Automation",
            value=(
                "`!setup_server` - Builds roles, categories, workspace rooms, and `#kanban-board`.\n"
                "`!setup_onboarding` - Deploys the role-selection panel in `#onboarding-portal`."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎫 JIRA Ticket Commands",
            value=(
                "• `!ticket create Title | Description | [Assignee] | [Priority] | [SP] | [Days] | [Start] | [End] | [Acceptance]`\n"
                "• `!ticket assign <LP-X> <@Member>`\n"
                "• `!ticket status <LP-X> <New/Planned/Refining/Active/Reviewing/Blocked/Closed>` (auto-archives when Closed)\n"
                "• `!ticket list` — active board from Neon Postgres\n"
                "• `!ticket view <LP-X>` — full details, comments & attachments"
            ),
            inline=False,
        )
        embed.add_field(
            name="🚀 Daily Standups & AI Blockers",
            value=(
                "• `!standup` - Opens a daily standup thread for updates.\n"
                "• `!blocker <details>` - Ask the **AI Scrum Master (Gemini)** for fast, expert unblocking advice.\n\n"
                "*Slash commands (`/ask`, `/board`, `/board_publish`, `/ticket_new`, `/ticket_move`, `/ticket_view`) are powered by the Cloudflare Worker Scrum Master.*"
            ),
            inline=False,
        )
        embed.set_footer(text="Launch Pixel DevOps Suite • Powered by NVIDIA NIM, Gemini & Neon PostgreSQL")
        await ctx.send(embed=embed)

    @commands.command(name="standup")
    async def standup(self, ctx: commands.Context) -> None:
        """Initiate a daily standup thread."""
        prompt = (
            "🚀 **Time for our Daily Standup!** 🚀\n\n"
            "Please reply in the thread with:\n"
            "1️⃣ What did you do yesterday?\n"
            "2️⃣ What are you doing today?\n"
            "3️⃣ Any blockers?\n"
        )
        msg = await ctx.send(prompt)
        try:
            await msg.create_thread(name=f"Standup - {datetime.now().strftime('%Y-%m-%d')}")
        except discord.errors.HTTPException as exc:
            logger.warning("Could not create standup thread: %s", exc)

    @commands.command(name="blocker")
    async def blocker(self, ctx: commands.Context, *, description: str) -> None:
        """Ask the AI Scrum Master (Dual-Brain) for help resolving a blocker."""
        council = getattr(getattr(self.bot, "app", None), "council", None)
        if council is None and not self.gemini_client:
            await ctx.send(
                "🧠 My AI brain isn't connected yet! Please add a valid `GEMINI_API_KEY` "
                "(and ideally `NVIDIA_API_KEY`) to the environment."
            )
            return

        prompt = (
            "A team member at 'Launch Pixel', a fast-moving product agency, reported "
            f"this blocker:\n\n\"{description}\"\n\n"
            "Respond with:\n"
            "1. A one-line diagnosis of the likely root cause.\n"
            "2. Two or three concrete, practical next steps to unblock.\n"
            "3. Who on a small agency team they should pair with, if relevant.\n"
            "Keep it under 140 words, encouraging and direct. Use Discord markdown."
        )

        # Prefer the Dual-Brain council (Nemotron lead + Gemini) so both brains
        # weigh in; fall back to a single Gemini shot if the council is absent.
        powered_by = "Dual-Brain (Nemotron + Gemini)"
        async with ctx.typing():
            try:
                if council is not None:
                    advice = await council.decide(prompt)
                    if not council.dual:
                        powered_by = "Gemini"
                else:
                    advice = await self._gemini(prompt)
                    powered_by = "Gemini"
            except Exception as exc:  # noqa: BLE001 - report to user
                logger.exception("Blocker generation failed")
                await ctx.send(f"⚠️ I had trouble thinking about that: {exc}")
                return

        embed = discord.Embed(
            title="💡 AI Scrum Master — Unblock Advice",
            description=advice or "*(no advice generated)*",
            color=0x9B5DE5,
        )
        embed.add_field(name="Reported Blocker", value=description[:1024], inline=False)
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Powered by {powered_by}")
        await ctx.send(embed=embed)

    # ================= HELPERS & ERROR HANDLERS =================

    async def _log_activity(self, guild: discord.Guild, message: str) -> None:
        """Post an activity line to the ticket activity feed if it exists."""
        channel = discord.utils.find(
            lambda c: c.name.lower() in ("ticket-activity-feed", "tickets-activity"),
            guild.text_channels,
        )
        if channel:
            try:
                await channel.send(message)
            except discord.errors.HTTPException as exc:
                logger.warning("Failed to post activity log: %s", exc)

    async def _handle_ticket_action(
        self, interaction: discord.Interaction, ticket_id: str, action: str
    ) -> None:
        """Callback for TaskView buttons — updates DB, Kanban tag, and channel."""
        status_map = {"done": "Reviewing", "blocked": "Blocked", "in_progress": "Active"}
        status = status_map.get(action, "Active")
        label = action.replace("_", " ").title()
        ticket_id = ticket_id.upper()

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "❌ This button only works inside a server.", ephemeral=True
            )
            return

        t = db.get_ticket(ticket_id)
        if not t:
            await interaction.response.send_message(f"❌ Ticket `{ticket_id}` not found!", ephemeral=True)
            return

        db.update_ticket_status(ticket_id, status)

        # Update the Kanban forum tag if the thread exists.
        if t.get("thread_id"):
            forum_channel = discord.utils.find(
                lambda c: c.name.lower() == "kanban-board", guild.forums
            )
            if forum_channel:
                thread = guild.get_thread(t["thread_id"])
                if thread:
                    try:
                        new_tag = discord.utils.find(
                            lambda tag: tag.name.lower() == status.lower(),
                            forum_channel.available_tags,
                        )
                        applied_tags = [new_tag] if new_tag else []
                        await thread.edit(applied_tags=applied_tags)
                    except Exception as exc:  # noqa: BLE001 - forum is optional
                        logger.warning("Failed to update forum tag: %s", exc)

        # Update the workspace channel topic if it exists.
        channel = guild.get_channel(t.get("channel_id")) if t.get("channel_id") else None
        if channel:
            await channel.send(
                f"🔄 Status changed to **{status}** via button ({interaction.user.name})."
            )

        await interaction.response.send_message(
            f"✅ Ticket **{ticket_id}** marked as {label}.", ephemeral=True
        )
        await self._log_activity(
            guild,
            f"🔄 **{interaction.user.name}** set **{ticket_id}** to {label} (button).",
        )

    @setup_server.error
    async def setup_server_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have Administrator permissions to run server setup!")

    @setup_onboarding.error
    async def setup_onboarding_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have Administrator permissions to deploy onboarding!")

    @blocker.error
    async def blocker_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Usage: `!blocker <describe what you are stuck on>`")


async def setup(bot: commands.Bot) -> None:
    """discord.py extension entry point (also usable via ``load_extension``)."""
    await bot.add_cog(LaunchPixelCog(bot))
