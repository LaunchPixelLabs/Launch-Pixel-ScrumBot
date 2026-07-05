import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
import threading
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from gmail_sync import GmailSync
import whatsapp_webhook
import db

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize Discord Bot
intents = discord.Intents.default()
intents.message_content = True
# Disabled privileged members intent to avoid developer portal restriction errors
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# Initialize Gemini Client if API key is present
gemini_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != 'your_gemini_api_key_here':
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Failed to initialize Gemini: {e}")

# Initialize Gmail Sync client
gmail_client_sync = GmailSync()


# File DB for Tickets
DB_FILE = 'tickets.json'

def load_tickets():
    if not os.path.exists(DB_FILE):
        return {"last_id": 0, "tickets": {}}
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {"last_id": 0, "tickets": {}}

def save_tickets(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving tickets: {e}")

class OnboardingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Core Associate", style=discord.ButtonStyle.blurple, custom_id="onboarding_core_associate")
    async def button_core(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name="Core Associate")
        if not role:
            try:
                role = await guild.create_role(name="Core Associate", color=discord.Color.blue(), hoist=True, mentionable=True)
            except discord.errors.Forbidden:
                await interaction.response.send_message("⚠️ **Administrative Warning:** The bot lacks permissions to create roles. Please ensure the `LP_Bot` role is dragged to the top of the Role Hierarchy in Server Settings.", ephemeral=True)
                return
            
        try:
            if role in interaction.user.roles:
                await interaction.response.send_message("💼 You already possess the **Core Associate** credential.", ephemeral=True)
            else:
                junior_role = discord.utils.get(guild.roles, name="Junior Associate")
                if junior_role and junior_role in interaction.user.roles:
                    await interaction.user.remove_roles(junior_role)
                await interaction.user.add_roles(role)
                await interaction.response.send_message("💼 Access Granted: You have been assigned the **Core Associate** credentials.", ephemeral=True)
        except discord.errors.Forbidden:
            await interaction.response.send_message("⚠️ **Administrative Warning:** The bot lacks permissions to assign this role. Please ensure the `LP_Bot` role is dragged to the top of the Role Hierarchy in Server Settings.", ephemeral=True)

    @discord.ui.button(label="Junior Associate", style=discord.ButtonStyle.success, custom_id="onboarding_junior_associate")
    async def button_junior(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name="Junior Associate")
        if not role:
            try:
                role = await guild.create_role(name="Junior Associate", color=discord.Color.green(), hoist=True, mentionable=True)
            except discord.errors.Forbidden:
                await interaction.response.send_message("⚠️ **Administrative Warning:** The bot lacks permissions to create roles. Please ensure the `LP_Bot` role is dragged to the top of the Role Hierarchy in Server Settings.", ephemeral=True)
                return
            
        try:
            if role in interaction.user.roles:
                await interaction.response.send_message("🌱 You already possess the **Junior Associate** credential.", ephemeral=True)
            else:
                core_role = discord.utils.get(guild.roles, name="Core Associate")
                if core_role and core_role in interaction.user.roles:
                    await interaction.user.remove_roles(core_role)
                await interaction.user.add_roles(role)
                await interaction.response.send_message("🌱 Access Granted: You have been assigned the **Junior Associate** (Internship) credentials.", ephemeral=True)
        except discord.errors.Forbidden:
            await interaction.response.send_message("⚠️ **Administrative Warning:** The bot lacks permissions to assign this role. Please ensure the `LP_Bot` role is dragged to the top of the Role Hierarchy in Server Settings.", ephemeral=True)

@bot.event
async def on_ready():
    print(f'🤖 {bot.user.name} has connected to Discord and is ready to Scrum!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Launch Pixel tickets | !ticket"))
    
    # Register persistent view
    bot.add_view(OnboardingView())
    print("🤖 Persistent Onboarding View Registered!")
    
    # Start the Gmail polling loop
    if not poll_gmail.is_running():
        poll_gmail.start()

# ================= SERVER AUTOMATION SETUP =================

@bot.command(name='setup_server')
@commands.has_permissions(administrator=True)
async def setup_server(ctx):
    """Automates Launch Pixel server layout, channels, and role hierarchy."""
    if not ctx.guild:
        await ctx.send("❌ This command must be used in a server!")
        return

    progress_msg = await ctx.send("⚡ **Initializing Launch Pixel Server Automation...**")

    # 1. Setup Roles
    await progress_msg.edit(content="⚡ **Creating Role Hierarchy...** ⏳")
    roles_config = [
        {"name": "👑 Founder / CEO", "color": 0xD4AF37},
        {"name": "📋 Product Manager (Scrum Master)", "color": 0x9B5DE5},
        {"name": "💻 Senior Dev", "color": 0x00F5D4},
        {"name": "🎨 UI/UX Designer", "color": 0xF15BB5},
        {"name": "🧪 QA Tester", "color": 0x2ECC71}
    ]
    
    created_roles = []
    for rc in roles_config:
        role = discord.utils.get(ctx.guild.roles, name=rc["name"])
        if not role:
            role = await ctx.guild.create_role(
                name=rc["name"],
                color=discord.Color(rc["color"]),
                hoist=True,
                mentionable=True
            )
            created_roles.append(f"Created {role.name}")
        else:
            created_roles.append(f"Found {role.name}")

    # 2. Setup Categories & Channels
    await progress_msg.edit(content="⚡ **Setting up Categories & Channels...** ⏳")
    
    categories = {
        "EXECUTIVE OVERSIGHT": [
            {"name": "exec-boardroom", "type": "text"},
            {"name": "enterprise-kpis", "type": "text"},
            {"name": "Boardroom Sync", "type": "voice"}
        ],
        "PROGRAM OPERATIONS": [
            {"name": "ticket-activity-feed", "type": "text"}
        ],
        "INTEGRATED COMMUNICATIONS": [
            {"name": "whatsapp-client-sync", "type": "text"},
            {"name": "external-email-tickets", "type": "text"},
            {"name": "incident-alerts", "type": "text"},
            {"name": "blocker-resolution", "type": "text"}
        ],
        "ENGINEERING & TECHNOLOGY": [
            {"name": "eng-governance", "type": "text"},
            {"name": "eng-sprint-backlog", "type": "text"},
            {"name": "Eng Architecture Sync", "type": "voice"},
            {"name": "Eng Daily Standup", "type": "voice"}
        ],
        "OPERATIONS & LOGISTICS": [
            {"name": "ops-governance", "type": "text"},
            {"name": "ops-sprint-backlog", "type": "text"},
            {"name": "Ops Operations Sync", "type": "voice"}
        ],
        "MARKETING & GROWTH": [
            {"name": "mkt-campaign-tracking", "type": "text"},
            {"name": "mkt-sprint-backlog", "type": "text"},
            {"name": "Mkt Campaign Sync", "type": "voice"}
        ],
        "FINANCE & TREASURY": [
            {"name": "fin-treasury-compliance", "type": "text"},
            {"name": "fin-invoice-tracking", "type": "text"},
            {"name": "Fin Treasury Review", "type": "voice"}
        ],
        "ACTIVE WORKSPACES": [],
        "ARCHIVED WORKSPACES": []
    }

    forum_error_msg = ""
    
    for cat_name, channels in categories.items():
        category = discord.utils.get(ctx.guild.categories, name=cat_name)
        if not category:
            category = await ctx.guild.create_category(name=cat_name)
        
        for ch in channels:
            ch_name = ch["name"]
            ch_type = ch["type"]
            
            if ch_type == "text":
                existing = discord.utils.find(lambda c: c.name.lower() == ch_name.lower() and c.category == category and isinstance(c, discord.TextChannel), ctx.guild.channels)
                if not existing:
                    await ctx.guild.create_text_channel(name=ch_name, category=category)
            elif ch_type == "voice":
                existing = discord.utils.find(lambda c: c.name.lower() == ch_name.lower() and c.category == category and isinstance(c, discord.VoiceChannel), ctx.guild.channels)
                if not existing:
                    await ctx.guild.create_voice_channel(name=ch_name, category=category)
        
        # Create Kanban board inside PROGRAM OPERATIONS
        if cat_name == "PROGRAM OPERATIONS":
            forum_ch = discord.utils.find(lambda c: c.name.lower() == "kanban-board" and c.category == category, ctx.guild.channels)
            if not forum_ch:
                tags = [
                    discord.ForumTag(name="New", emoji="🆕"),
                    discord.ForumTag(name="Planned", emoji="📅"),
                    discord.ForumTag(name="Active", emoji="▶️"),
                    discord.ForumTag(name="Refining", emoji="🔧"),
                    discord.ForumTag(name="Resolved", emoji="✅"),
                    discord.ForumTag(name="Closed", emoji="📁"),
                ]
                try:
                    await ctx.guild.create_forum(
                        name="kanban-board",
                        category=category,
                        available_tags=tags,
                        topic="Project Kanban Board - Create tasks using !ticket create!"
                    )
                except discord.errors.HTTPException as e:
                    if e.code == 40041:
                        forum_error_msg = "\n⚠️ *Note: Could not create forum channel '#kanban-board' because **Community Features** are not enabled in your Server Settings.*"
                    else:
                        forum_error_msg = f"\n⚠️ *Forum creation failed: {e.text}*"

    # Complete!
    success_embed = discord.Embed(
        title="🎉 Launch Pixel Server Setup Complete!",
        description="I have automatically set up your roles, operational text rooms, and voice channels.",
        color=0xD4AF37
    )
    success_embed.add_field(name="Hierarchy Roles", value="\n".join([f"🔹 {rc['name']}" for rc in roles_config]), inline=True)
    success_embed.add_field(name="Operations Channels", value="✅ Info & Stats\n✅ Workspace & Chats\n✅ Dev / Design / QA Rooms\n✅ Custom Voice Channels\n✅ DevOps & Alerts", inline=True)
    
    if forum_error_msg:
        success_embed.add_field(name="Kanban Forum Status", value=forum_error_msg, inline=False)
    else:
        success_embed.add_field(name="Kanban Forum Status", value="📋 `#kanban-board` has been created with New, Planned, Active, Refining, Resolved, and Closed tags!", inline=False)

    await progress_msg.delete()
    await ctx.send(embed=success_embed)

@bot.command(name='setup_onboarding')
@commands.has_permissions(administrator=True)
async def setup_onboarding(ctx):
    """Deploys the professional onboarding verification panel into #onboarding-portal."""
    if not ctx.guild:
        await ctx.send("❌ This command must be used in a server!")
        return

    channel = discord.utils.find(lambda c: c.name.lower() == "onboarding-portal", ctx.guild.text_channels)
    if not channel:
        await ctx.send("❌ Could not find `#onboarding-portal` text channel! Please run `!setup_server` first.")
        return

    try:
        await channel.purge(limit=100)
    except Exception:
        pass

    embed = discord.Embed(
        title="🏢 LAUNCH PIXEL • ENTERPRISE ONBOARDING PORTAL",
        description=(
            "Welcome to the **Launch Pixel Core Operations Workspace**. To initiate your corporate onboarding and secure access to your designated tracking channels, please verify your credentials below:\n\n"
            "**💼 CORE ASSOCIATE (Regular Staff)**\n"
            "Select this option if you are a full-time partner, director, engineer, marketer, or operational manager.\n\n"
            "**🌱 JUNIOR ASSOCIATE (Internship Program)**\n"
            "Select this option if you are currently enrolled in our professional internship program."
        ),
        color=0xD4AF37
    )
    embed.set_footer(text="Launch Pixel Security & Credentials System • Select to Assign Role")

    await channel.send(embed=embed, view=OnboardingView())
    await ctx.send(f"✅ Onboarding verification panel deployed successfully inside {channel.mention}!")


# ================= JIRA TICKETING SYSTEM =================

@bot.group(name='ticket', invoke_without_command=True)
async def ticket_group(ctx):
    """JIRA-style ticket operations using Neon PostgreSQL database."""
    embed = discord.Embed(
        title="🎫 Launch Pixel DevOps Bot",
        description="JIRA/Azure DevOps task management integrated with serverless Neon Postgres.",
        color=0x9B5DE5
    )
    embed.add_field(name="🆕 Create Ticket", value="`!ticket create <Title> | <Description> | [Assignee] | [Priority] | [Story Points] | [Days] | [Start] | [End] | [Acceptance]`", inline=False)
    embed.add_field(name="👤 Assign Member", value="`!ticket assign <LP-X> <@Member>`", inline=False)
    embed.add_field(name="▶️ Update Status", value="`!ticket status <LP-X> <New|Planned|Active|Refining|Resolved|Closed>`", inline=False)
    embed.add_field(name="📋 List Tickets", value="`!ticket list`", inline=False)
    embed.add_field(name="🔍 View Details & Comments", value="`!ticket view <LP-X>`", inline=False)
    await ctx.send(embed=embed)

@ticket_group.command(name='create')
async def ticket_create(ctx, *, args: str):
    """Creates a ticket in PostgreSQL, updates the Kanban Board, and spins up a dedicated channel."""
    if not ctx.guild:
        await ctx.send("❌ This command must be used in a server!")
        return

    parts = [p.strip() for p in args.split('|')]
    if len(parts) < 2:
        await ctx.send("❌ Syntax error! Use: `!ticket create Title | Description | [Assignee] | [Priority] | [Story Points] | [Days] | [Start Date] | [End Date] | [Acceptance Criteria]`")
        return

    title = parts[0]
    description = parts[1]
    assignee_raw = parts[2] if len(parts) > 2 and parts[2] else "Unassigned"
    priority = parts[3] if len(parts) > 3 and parts[3] else "Medium"
    story_points = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1
    priority_days = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 5
    start_date_str = parts[6] if len(parts) > 6 and parts[6] else datetime.now().strftime("%Y-%m-%d")
    end_date_str = parts[7] if len(parts) > 7 and parts[7] else datetime.now().strftime("%Y-%m-%d")
    acceptance_criteria = parts[8] if len(parts) > 8 and parts[8] else "No specific acceptance criteria specified."

    # Try resolving assignee member if mentioned
    assignee_member = None
    if assignee_raw.startswith('<@') and assignee_raw.endswith('>'):
        try:
            member_id = int(assignee_raw.replace('<@', '').replace('>', '').replace('!', ''))
            assignee_member = ctx.guild.get_member(member_id)
            if not assignee_member:
                try:
                    assignee_member = await ctx.guild.fetch_member(member_id)
                except Exception:
                    pass
        except ValueError:
            pass

    # Retrieve next incrementing ID
    next_num = db.get_last_ticket_id() + 1
    ticket_id = f"LP-{next_num}"

    # 1. Create a dedicated text channel for the ticket
    ticket_category = discord.utils.get(ctx.guild.categories, name="ACTIVE WORKSPACES")
    if not ticket_category:
        ticket_category = await ctx.guild.create_category(name="ACTIVE WORKSPACES")
        
    clean_title = "".join(c if c.isalnum() else "-" for c in title.lower()).replace("--", "-").strip("-")
    channel_name = f"lp-ticket-{next_num}-{clean_title}"[:100]
    
    topic_str = f"{ticket_id}: {title} | Assignee: {assignee_member.display_name if assignee_member else assignee_raw} | SP: {story_points} | Priority: {priority}"
    ticket_channel = await ctx.guild.create_text_channel(name=channel_name, category=ticket_category, topic=topic_str)

    # 2. Add to Kanban forum channel if it exists
    forum_channel = discord.utils.find(lambda c: c.name.lower() == "kanban-board", ctx.guild.forums)
    thread_id = None
    
    if forum_channel:
        new_tag = discord.utils.find(lambda t: t.name.lower() == "new", forum_channel.available_tags)
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
            thread = await forum_channel.create_thread(
                name=f"[{ticket_id}] {title}",
                content=forum_content,
                applied_tags=applied_tags
            )
            thread_id = thread.id
        except Exception as e:
            print(f"Failed to post to Kanban Forum: {e}")

    # 3. Store ticket in Neon Database
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
        channel_id=ticket_channel.id
    )

    # 4. Notify & Log
    embed = discord.Embed(
        title=f"🆕 Ticket Created: {ticket_id}",
        description=f"**Title:** {title}\n**Story Points:** {story_points} SP\n**Assignee:** {assignee_raw}",
        color=0x2ECC71
    )
    embed.add_field(name="Discussion Channel", value=ticket_channel.mention, inline=True)
    if thread_id:
        embed.add_field(name="Kanban Board Card", value=f"[Go to Card](https://discord.com/channels/{ctx.guild.id}/{forum_channel.id}/{thread_id})", inline=True)
        
    await ctx.send(embed=embed)

    # Message inside the ticket channel
    welcome_embed = discord.Embed(
        title=f"🎫 {ticket_id} - Task Workspace",
        description=f"This channel is dedicated to the discussion and execution of: **{title}**.\n\n**Goal Description:**\n{description}",
        color=0x9B5DE5
    )
    welcome_embed.add_field(name="Story Points", value=f"{story_points} SP", inline=True)
    welcome_embed.add_field(name="Assignee", value=assignee_raw, inline=True)
    welcome_embed.add_field(name="Priority (Days)", value=f"{priority} ({priority_days} days)", inline=True)
    welcome_embed.add_field(name="Timelines", value=f"📅 {start_date_str} to {end_date_str}", inline=False)
    welcome_embed.add_field(name="Acceptance Criteria", value=acceptance_criteria, inline=False)
    
    welcome_embed.set_footer(text="Writing messages or uploading files here will automatically log comments/attachments to the Neon database!")
    await ticket_channel.send(embed=welcome_embed)

    # Log to tickets-activity channel if it exists
    activity_channel = discord.utils.find(lambda c: c.name.lower() == "tickets-activity", ctx.guild.text_channels)
    if activity_channel:
        await activity_channel.send(f"🆕 **{ctx.author.name}** created ticket **{ticket_id}**: *{title}* (SP: {story_points}, Assigned to: {assignee_raw})")

@ticket_group.command(name='assign')
async def ticket_assign(ctx, ticket_id: str, member: discord.Member):
    """Assigns an existing ticket to a team member inside Neon PostgreSQL."""
    if not ctx.guild:
        await ctx.send("❌ This command must be used in a server!")
        return

    ticket_id = ticket_id.upper()
    t = db.get_ticket(ticket_id)
    
    if not t:
        await ctx.send(f"❌ Ticket `{ticket_id}` not found!")
        return

    db.update_ticket_assignee(ticket_id, member.id, member.display_name)

    # 1. Update active text channel topic if channel exists
    channel = ctx.guild.get_channel(t["channel_id"])
    if channel:
        await channel.edit(topic=f"{t['id']}: {t['title']} | Assignee: {member.display_name} | SP: {t['story_points']}")
        await channel.send(f"👤 **{member.mention}** has been assigned to this ticket by {ctx.author.name}!")

    # 2. Update forum thread description if exists
    forum_channel = discord.utils.find(lambda c: c.name.lower() == "kanban-board", ctx.guild.forums)
    if forum_channel and t["thread_id"]:
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
        except Exception as e:
            print(f"Failed to update forum thread details: {e}")

    await ctx.send(f"✅ Ticket **{ticket_id}** has been assigned to **{member.display_name}**.")

    # Log to tickets-activity
    activity_channel = discord.utils.find(lambda c: c.name.lower() == "tickets-activity", ctx.guild.text_channels)
    if activity_channel:
        await activity_channel.send(f"👤 **{ctx.author.name}** assigned **{ticket_id}** to **{member.display_name}**")

@ticket_group.command(name='status')
async def ticket_status(ctx, ticket_id: str, status: str):
    """Updates status, modifies Kanban Board, and manages dynamic ticket channels inside Neon PostgreSQL."""
    if not ctx.guild:
        await ctx.send("❌ This command must be used in a server!")
        return

    ticket_id = ticket_id.upper()
    status = status.capitalize()
    
    valid_statuses = ["New", "Planned", "Active", "Refining", "Resolved", "Closed"]
    if status not in valid_statuses:
        await ctx.send(f"❌ Invalid status! Choose from: `New`, `Planned`, `Active`, `Refining`, `Resolved`, `Closed`")
        return

    t = db.get_ticket(ticket_id)
    if not t:
        await ctx.send(f"❌ Ticket `{ticket_id}` not found!")
        return

    old_status = t["status"]
    db.update_ticket_status(ticket_id, status)

    # 1. Update Forum Tag if exists
    forum_channel = discord.utils.find(lambda c: c.name.lower() == "kanban-board", ctx.guild.forums)
    if forum_channel and t["thread_id"]:
        try:
            thread = ctx.guild.get_thread(t["thread_id"])
            if thread:
                new_tag = discord.utils.find(lambda t: t.name.lower() == status.lower(), forum_channel.available_tags)
                applied_tags = [new_tag] if new_tag else []
                await thread.edit(applied_tags=applied_tags)
        except Exception as e:
            print(f"Failed to update forum tag: {e}")

    # 2. Inform the ticket discussion channel
    channel = ctx.guild.get_channel(t["channel_id"])
    if channel:
        await channel.send(f"🔄 Status changed: **{old_status}** ➡️ **{status}** (updated by {ctx.author.name})")

    # 3. Handle Auto-Archiving if Closed or Resolved
    if status in ["Closed", "Resolved"] and channel:
        archive_category = discord.utils.find(lambda c: c.name.lower() == "archived workspaces", ctx.guild.categories)
        if not archive_category:
            archive_category = await ctx.guild.create_category(name="ARCHIVED WORKSPACES")
            
        await channel.send(f"📁 **Notice:** This ticket is now **{status}**. Moving to archived channels and locking in 5 seconds...")
        await asyncio.sleep(5)
        
        try:
            # Shift category
            await channel.edit(category=archive_category)
            # Remove send messages permission for default role
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            await channel.send("🔒 *This workspace is now archived and read-only.*")
        except Exception as e:
            await channel.send(f"⚠️ Failed to complete archiving permissions: {e}")

    await ctx.send(f"✅ Ticket **{ticket_id}** status updated to **{status}**.")

    # Log to tickets-activity
    activity_channel = discord.utils.find(lambda c: c.name.lower() == "tickets-activity", ctx.guild.text_channels)
    if activity_channel:
        await activity_channel.send(f"🔄 **{ctx.author.name}** updated status of **{ticket_id}** to **{status}**")

@ticket_group.command(name='list')
async def ticket_list(ctx):
    """Lists all active (non-Closed) tickets querying the Neon Postgres DB."""
    active_tickets = db.get_active_tickets()

    if not active_tickets:
        await ctx.send("📋 There are currently no active tickets! Use `!ticket create` to get started.")
        return

    embed = discord.Embed(
        title="📋 Launch Pixel - Active Tickets Board",
        description="Here are the currently active tasks loaded from Neon serverless Postgres:",
        color=0xD4AF37
    )

    for t in active_tickets:
        channel_mention = f"<#{t['channel_id']}>" if t.get("channel_id") else "No channel"
        end_date_fmt = t['end_date'].strftime("%Y-%m-%d") if t.get('end_date') else "Not set"
        embed.add_field(
            name=f"[{t['id']}] {t['title']}",
            value=(
                f"👤 **Assignee:** {t['assignee_name']} | 🚀 **Points:** `{t['story_points']} SP`\n"
                f"⚡ **Priority:** {t['priority']} ({t['priority_days']} days) | 🔄 **Status:** `{t['status']}`\n"
                f"📅 **Due Date:** {end_date_fmt} | 💬 Workspace: {channel_mention}"
            ),
            inline=False
        )

    await ctx.send(embed=embed)

@ticket_group.command(name='view')
async def ticket_view(ctx, ticket_id: str):
    """Pulls detailed JIRA-style ticket sheet alongside comments & attachments from Neon."""
    ticket_id = ticket_id.upper()
    t = db.get_ticket(ticket_id)
    
    if not t:
        await ctx.send(f"❌ Ticket `{ticket_id}` not found in Neon database!")
        return

    # Select color based on priority
    colors = {
        "high": 0xE74C3C,
        "medium": 0xF39C12,
        "low": 0x3498DB
    }
    color = colors.get(t["priority"].lower(), 0x9B5DE5)

    embed = discord.Embed(
        title=f"🎫 {t['id']}: {t['title']}",
        description=t["description"] or "*No description provided*",
        color=color
    )
    embed.add_field(name="👤 Assignee", value=t["assignee_name"], inline=True)
    embed.add_field(name="🚀 Story Points", value=f"{t['story_points']} SP", inline=True)
    embed.add_field(name="🔄 Status", value=f"`{t['status']}`", inline=True)
    
    embed.add_field(name="⚡ Priority", value=f"{t['priority']} ({t['priority_days']} days)", inline=True)
    start_fmt = t['start_date'].strftime("%Y-%m-%d") if t['start_date'] else "Not set"
    end_fmt = t['end_date'].strftime("%Y-%m-%d") if t['end_date'] else "Not set"
    embed.add_field(name="📅 Timelines", value=f"{start_fmt} to {end_fmt}", inline=True)
    
    channel_mention = f"<#{t['channel_id']}>" if t.get("channel_id") else "None"
    embed.add_field(name="💬 Workspace Channel", value=channel_mention, inline=True)
    
    embed.add_field(name="📝 Acceptance Criteria", value=t["acceptance_criteria"] or "*None specified*", inline=False)

    # 1. Grab attachments from Neon Postgres
    attachments = db.get_ticket_attachments(ticket_id)
    if attachments:
        attach_text = ""
        for a in attachments:
            attach_text += f"📂 [{a['file_name']}]({a['file_url']})\n"
        embed.add_field(name="📎 Attachments, Files & Links", value=attach_text, inline=False)
        
    # 2. Grab recent updates / comments from Neon Postgres
    comments = db.get_ticket_comments(ticket_id)
    if comments:
        comment_text = ""
        for c in comments[-5:]: # Get last 5 comments
            date_str = c['created_at'].strftime("%m-%d %H:%M")
            comment_text += f"💬 **{c['author_name']}** ({date_str}): {c['comment_text']}\n"
        embed.add_field(name="💬 Recent Workspace Updates", value=comment_text, inline=False)

    forum_channel = discord.utils.find(lambda c: c.name.lower() == "kanban-board", ctx.guild.forums)
    if forum_channel and t["thread_id"]:
        embed.add_field(name="📋 Kanban Card", value=f"[Go to Card](https://discord.com/channels/{ctx.guild.id}/{forum_channel.id}/{t['thread_id']})", inline=True)

    embed.set_footer(text=f"Task logged in Neon Postgres Serverless DB")
    await ctx.send(embed=embed)


# ================= STANDUP & AI BLOCKER RESOLUTION =================

@bot.command(name='help')
async def help_command(ctx):
    """Premium custom help command for Launch Pixel DevOps Bot."""
    embed = discord.Embed(
        title="🤖 Launch Pixel DevOps Bot - Help Guide",
        description="Here is your complete manual for the Launch Pixel automated server & DevOps tracking system.",
        color=0xD4AF37 # Premium Gold
    )
    
    embed.add_field(
        name="⚡ Server Automation",
        value="`!setup_server` - Automatically builds roles, channel categories, workspace rooms, and registers `#kanban-board` in Discord.",
        inline=False
    )
    
    embed.add_field(
        name="🎫 JIRA Ticket Commands",
        value=(
            "• `!ticket create Title | Description | [Assignee] | [Priority] | [SP] | [Days] | [Start] | [End] | [Acceptance]`\n"
            "  *Creates a ticket, logs it to Neon, spins up a workspace channel, and adds a Kanban card.*\n"
            "• `!ticket assign <LP-X> <@Member>` - Assigns the task to a team member in Neon DB.\n"
            "• `!ticket status <LP-X> <New/Planned/Active/Refining/Resolved/Closed>` - Shifts ticket state, moves Kanban card tag, and **auto-archives** completed rooms.\n"
            "• `!ticket list` - Renders an active JIRA task board pulled directly from Neon Postgres.\n"
            "• `!ticket view <LP-X>` - Displays complete ticket details, recent comments, and downloadable attachment files from Neon DB."
        ),
        inline=False
    )
    
    embed.add_field(
        name="🚀 Daily Standups & AI Blockers",
        value=(
            "• `!standup` - Starts a daily standup check-in and opens a dedicated daily thread for updates.\n"
            "• `!blocker <details>` - Pings the **AI Scrum Master (Gemini)** to get fast, expert advice to resolve coding or design blockers."
        ),
        inline=False
    )
    
    embed.add_field(
        name="🕵️‍♂️ AI Scrum Master Bot (Prefix '?')",
        value="Once activated with a secondary token, the Scrum Bot monitors active workspaces. Any chat you send is logged as a comment, and the AI scans messages using Gemini, instantly sending alert cards to `#blockers` when anyone is stuck!",
        inline=False
    )

    embed.set_footer(text="Launch Pixel DevOps Suite • Powered by Cloudflare Edge & Neon PostgreSQL")
    await ctx.send(embed=embed)


@bot.command(name='standup')
async def standup(ctx):
    """Initiates a daily standup thread."""
    prompt = (
        "🚀 **Time for our Daily Standup!** 🚀\n\n"
        "Please reply in the thread with:\n"
        "1️⃣ What did you do yesterday?\n"
        "2️⃣ What are you doing today?\n"
        "3️⃣ Any blockers?\n"
    )
    msg = await ctx.send(prompt)
    await msg.create_thread(name=f"Standup - {datetime.now().strftime('%Y-%m-%d')}")

@bot.command(name='blocker')
async def blocker(ctx, *, description: str):
    """Ask the AI Scrum Master for help resolving a blocker."""
    if not gemini_client:
        await ctx.send("🧠 My AI brain isn't connected yet! Please add a valid GEMINI_API_KEY to the `.env` file.")
        return
        
    await ctx.send("🤔 Let me think about how to unblock you...")
    
    try:
        prompt = (
            f"You are an expert Agile Scrum Master helping a 5-person agency called 'Launch Pixel'. "
            f"A team member has reported the following blocker: '{description}'. "
            f"Provide a concise, encouraging, and highly practical suggestion (max 3 sentences) "
            f"on how they can overcome this blocker or who they should talk to."
        )
        
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        await ctx.send(f"💡 **AI Scrum Master Advice:**\n{response.text}")
    except Exception as e:
        await ctx.send(f"❌ Oops, I had trouble thinking about that: {str(e)}")

# Fallback error handlers
@setup_server.error
async def setup_server_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have Administrator permissions to run server setup!")

# ================= INTEGRATIONS & WEBHOOKS =================

@tasks.loop(minutes=2)
async def poll_gmail():
    """Polls Gmail for unread messages and uses Gemini to summarize them as Scrum Master."""
    if not gmail_client_sync.is_configured:
        return

    try:
        emails = gmail_client_sync.fetch_latest_emails(max_results=5)
        if not emails:
            return

        for email in emails:
            for guild in bot.guilds:
                channel = discord.utils.find(lambda c: c.name.lower() == "client-emails", guild.text_channels)
                if channel:
                    summary_text = "*(AI Scrum Master key not configured - showing raw preview)*\n\n" + email["body"][:400]
                    if gemini_client:
                        try:
                            prompt = (
                                f"You are the expert Agile Scrum Master for 'Launch Pixel' (a 5-person agency). We received an email:\n"
                                f"From: {email['sender']}\n"
                                f"Subject: {email['subject']}\n"
                                f"Body: {email['body']}\n\n"
                                f"Summarize this email in exactly 3-4 professional, action-oriented sentences. "
                                f"Outline: 1) What the client wants, 2) Key ticket items to create, 3) Immediate blockers for our team."
                            )
                            response = gemini_client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=prompt
                            )
                            summary_text = response.text
                        except Exception as e:
                            print(f"Failed to summarize email via Gemini: {e}")
                    
                    embed = discord.Embed(
                        title=f"✉️ Client Email: {email['subject']}",
                        description=summary_text,
                        color=0x3498DB
                    )
                    embed.add_field(name="From", value=email["sender"], inline=True)
                    embed.add_field(name="Date", value=email["date"], inline=True)
                    embed.set_footer(text="Summarized by LP AI Scrum Master")
                    
                    await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Error polling Gmail: {e}")

async def post_whatsapp_to_discord(sender_name, sender_phone, body):
    """Coro to post WhatsApp message to the whatsapp-sync channel."""
    for guild in bot.guilds:
        channel = discord.utils.find(lambda c: c.name.lower() == "whatsapp-sync", guild.text_channels)
        if channel:
            embed = discord.Embed(
                title="💬 WhatsApp Chat Sync",
                description=body,
                color=0x2ECC71
            )
            embed.add_field(name="From", value=sender_name, inline=True)
            embed.add_field(name="Phone", value=sender_phone, inline=True)
            embed.set_footer(text="Synced via LP WhatsApp Webhook")
            await channel.send(embed=embed)

def handle_whatsapp_message(sender_name, sender_phone, body):
    """Callback triggered by the Flask thread when a new WhatsApp message arrives."""
    coro = post_whatsapp_to_discord(sender_name, sender_phone, body)
    asyncio.run_coroutine_threadsafe(coro, bot.loop)

# Register WhatsApp callback
whatsapp_webhook.whatsapp_callback = handle_whatsapp_message

# Start Flask server in background thread
def start_webhook_server():
    print("🌐 [Flask Webhook] Launching WhatsApp sync endpoint at http://localhost:5001/webhook...")
    try:
        whatsapp_webhook.run_server(port=5001)
    except Exception as e:
        print(f"⚠️ Flask Webhook failed to start: {e}")

webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
webhook_thread.start()

bot.run(DISCORD_TOKEN)
