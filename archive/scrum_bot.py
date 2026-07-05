import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from google import genai
import db

# Load environment variables
load_dotenv()
SCRUM_BOT_TOKEN = os.getenv('SCRUM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize Scrum Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='?', intents=intents)  # Using different prefix '?' to avoid command collisions!
bot.remove_command('help')

# Initialize Gemini Client if API key is present
gemini_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != 'your_gemini_api_key_here':
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Failed to initialize Gemini: {e}")

@bot.event
async def on_ready():
    print(f'🕵️‍♂️ {bot.user.name} (AI Scrum Master Bot) is online and monitoring tasks!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="developer updates | ?scrumcheck"))
    
    # Start the automated daily scrum check loop
    if not daily_scrum_sweep.is_running():
        daily_scrum_sweep.start()

# ================= BACKGROUND ACTIVE SCRUM SURVEY =================

@tasks.loop(hours=24)
async def daily_scrum_sweep():
    """Performs an automated check on all active tickets once a day."""
    await run_scrum_check_sweep()

async def run_scrum_check_sweep(ctx=None):
    """Loops through all active tickets, checks in with developers, and requests updates."""
    active_tickets = db.get_active_tickets()
    
    if not active_tickets:
        if ctx:
            await ctx.send("📋 There are no active tickets to verify at the moment!")
        return

    target = ctx if ctx else bot
    print(f"⚙️ Running automated scrum check sweep on {len(active_tickets)} tickets...")

    for t in active_tickets:
        channel_id = t["channel_id"]
        # Find the text channel in the guild
        for guild in bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                assignee_mention = f"<@{t['assignee_id']}>" if t["assignee_id"] else t["assignee_name"]
                
                check_embed = discord.Embed(
                    title="🕵️‍♂️ Daily Scrum Check-In",
                    description=(
                        f"Hey {assignee_mention}, just checking in on your active ticket **{t['id']}: {t['title']}**!\n\n"
                        f"⏳ **End Date:** {t['end_date'] or 'Not set'} | 🚀 **Story Points:** {t['story_points']}\n"
                        f"Please write a quick status update in this channel: \n"
                        f"1. Is everything on track?\n"
                        f"2. **Are you stuck or facing any blockers?** *(Use the keyword **stuck** if you need help)*"
                    ),
                    color=0x9B5DE5
                )
                await channel.send(embed=check_embed)
                await asyncio.sleep(1) # Rate limit protection

    if ctx:
        await ctx.send(f"✅ Manual scrum check sweep triggered! Surveyed {len(active_tickets)} active ticket channels.")

# ================= AUTO SCAN COMMENTS, ATTACHMENTS & STUCK ALERTS =================

@bot.event
async def on_message(message):
    """Listens to active ticket channels, logs comments/attachments, and scans all communications for incidents."""
    # Ignore own messages
    if message.author.bot:
        return

    # Let bot process commands first
    await bot.process_commands(message)

    channel_name = message.channel.name.lower()

    # ---------------- CASE 1: TICKET DISCUSSION CHANNELS ----------------
    if channel_name.startswith("lp-ticket-") or channel_name.startswith("lp-incident-"):
        # Extract ticket ID from database
        active_tickets = db.get_active_tickets()
        current_ticket = None
        for t in active_tickets:
            if t["channel_id"] == message.channel.id:
                current_ticket = t
                break

        if not current_ticket:
            return

        ticket_id = current_ticket["id"]
        author_name = message.author.display_name
        author_id = message.author.id

        # 1. Capture attachments (links, files, images) to Postgres
        for attachment in message.attachments:
            db.add_attachment(ticket_id, attachment.filename, attachment.url)
            await message.channel.send(f"📂 *Logged attachment: **{attachment.filename}** to Neon DB!*")

        # Capture URL links
        words = message.content.split()
        for w in words:
            if w.startswith("http://") or w.startswith("https://"):
                db.add_attachment(ticket_id, "External Link", w)
                await message.channel.send(f"🔗 *Logged URL link to Neon DB!*")

        # 2. Log message as a Comment to Neon
        if message.content.strip():
            db.add_comment(ticket_id, author_id, author_name, message.content)

        # 3. Blocker Scan via Gemini AI
        if gemini_client and message.content.strip():
            try:
                prompt = (
                    f"You are the AI Scrum Master checking a team member's update.\n"
                    f"Developer: {author_name}\n"
                    f"Active Task: {current_ticket['title']}\n"
                    f"Update Message: '{message.content}'\n\n"
                    f"Determine if the developer is STUCK or facing a blocker that prevents them from finishing this task.\n"
                    f"Respond in EXACTLY the following format:\n"
                    f"STUCK: [True/False]\n"
                    f"SUMMARY: [If stuck, write a 1-sentence description of what is blocking them. If not stuck, write a 1-sentence summary of their progress.]"
                )
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                
                ai_reply = response.text.strip()
                is_stuck = False
                summary = ""
                for line in ai_reply.split('\n'):
                    if line.startswith("STUCK:"):
                        is_stuck = "true" in line.lower()
                    elif line.startswith("SUMMARY:"):
                        summary = line.replace("SUMMARY:", "").strip()

                if is_stuck:
                    await alert_scrum_admin(message.guild, current_ticket, message.author, summary)
                    alert_embed = discord.Embed(
                        title="🚨 Blocker Flagged",
                        description=(
                            f"🧠 **AI Scrum Master:** I've flagged that you are stuck on this task!\n"
                            f"**Blocker detail:** {summary}\n\n"
                            f"I have alerted the Product Manager and Admin to unblock you immediately."
                        ),
                        color=0xE74C3C
                    )
                    await message.channel.send(embed=alert_embed)
                else:
                    print(f"🕵️‍♂️ Scrum update registered for {ticket_id}: {summary}")
            except Exception as e:
                print(f"⚠️ Failed to analyze developer status: {e}")

    # ---------------- CASE 2: CORE CHANNELS (INCIDENT SCANNING) ----------------
    elif channel_name in ["exec-boardroom", "eng-sprint-backlog", "external-email-tickets", "whatsapp-client-sync", "incident-alerts"]:
        if gemini_client and message.content.strip():
            try:
                # Ask Gemini if this is an outage or emergency incident
                prompt = (
                    f"You are the expert AI Scrum Master for 'Launch Pixel' (a 5-person agency).\n"
                    f"A message was received in #{channel_name} from '{message.author.display_name}':\n"
                    f"\"{message.content}\"\n\n"
                    f"Determine if this message represents a critical system incident, server crash, database outage, major client emergency, or critical bug that demands immediate action.\n"
                    f"Respond in EXACTLY the following format:\n"
                    f"INCIDENT: [True/False]\n"
                    f"TITLE: [Brief, descriptive ticket title, e.g. 'INCIDENT: Database Outage']\n"
                    f"SUMMARY: [1-sentence summary of the emergency]\n"
                    f"SEVERITY: [High/Critical]"
                )
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                
                ai_reply = response.text.strip()
                is_incident = False
                title = ""
                summary = ""
                severity = "High"
                
                for line in ai_reply.split('\n'):
                    if line.startswith("INCIDENT:"):
                        is_incident = "true" in line.lower()
                    elif line.startswith("TITLE:"):
                        title = line.replace("TITLE:", "").strip()
                    elif line.startswith("SUMMARY:"):
                        summary = line.replace("SUMMARY:", "").strip()
                    elif line.startswith("SEVERITY:"):
                        severity = line.replace("SEVERITY:", "").strip()

                if is_incident:
                    # 1. Allocate ID
                    next_num = db.get_last_ticket_id() + 1
                    ticket_id = f"LP-{next_num}"

                    # 2. Spin up dedicated incident discussion room
                    category = discord.utils.get(message.guild.categories, name="ACTIVE WORKSPACES")
                    if not category:
                        category = await message.guild.create_category(name="ACTIVE WORKSPACES")
                        
                    clean_title = "".join(c if c.isalnum() else "-" for c in title.lower()).replace("--", "-").strip("-")
                    channel_name_format = f"lp-incident-{next_num}-{clean_title}"[:100]
                    
                    incident_channel = await message.guild.create_text_channel(
                        name=channel_name_format,
                        category=category,
                        topic=f"🔥 EMERGENCY INCIDENT {ticket_id}: {title} | Severity: {severity}"
                    )

                    # 3. Create JIRA ticket in Neon Postgres DB
                    db.create_ticket(
                        ticket_id=ticket_id,
                        title=title,
                        description=f"[INCIDENT FLAG] {summary}\nOriginal report: {message.content}",
                        assignee_id=None,
                        assignee_name="Unassigned",
                        priority=severity,
                        priority_days=1,
                        start_date=datetime.now().strftime("%Y-%m-%d"),
                        end_date=datetime.now().strftime("%Y-%m-%d"),
                        story_points=5,
                        acceptance_criteria="1. Identify root cause of outage.\n2. Deploy emergency hotfix.\n3. Restore stable services.\n4. Write incident post-mortem.",
                        thread_id=None,
                        channel_id=incident_channel.id
                    )

                    # 4. Create Kanban Forum Card if exists
                    forum_channel = discord.utils.find(lambda c: c.name.lower() == "kanban-board", message.guild.forums)
                    if forum_channel:
                        new_tag = discord.utils.find(lambda t: t.name.lower() == "new", forum_channel.available_tags)
                        applied_tags = [new_tag] if new_tag else []
                        forum_content = (
                            f"🔥 **EMERGENCY INCIDENT TICKET**\n"
                            f"**Ticket ID:** `{ticket_id}`\n"
                            f"**Severity:** `{severity}`\n"
                            f"**Workspace Room:** {incident_channel.mention}\n\n"
                            f"**Incident Summary:**\n{summary}\n\n"
                            f"**Original Report:**\n{message.content}"
                        )
                        try:
                            await forum_channel.create_thread(
                                name=f"🔥 [{ticket_id}] {title}",
                                content=forum_content,
                                applied_tags=applied_tags
                            )
                        except Exception as e:
                            print(f"Failed to post incident to Kanban: {e}")

                    # 5. Alert in workspace & raise it in the chat
                    founder_role = discord.utils.get(message.guild.roles, name="👑 Founder / CEO")
                    pm_role = discord.utils.get(message.guild.roles, name="📋 Product Manager (Scrum Master)")
                    ping_str = ""
                    if founder_role:
                        ping_str += f"{founder_role.mention} "
                    if pm_role:
                        ping_str += f"{pm_role.mention} "

                    alert_embed = discord.Embed(
                        title=f"🚨 CRITICAL INCIDENT DETECTED: {ticket_id}",
                        description=(
                            f"🔥 **AI Scrum Master Warning:** I have detected a critical incident in #{message.channel.name}!\n\n"
                            f"**Incident:** {summary}\n"
                            f"**Logged Ticket:** `{ticket_id}`\n"
                            f"**Severity:** `{severity}`\n"
                            f"**Original Report:** *\"{message.content}\"* (by {message.author.display_name})"
                        ),
                        color=0xE74C3C,
                        timestamp=datetime.now()
                    )
                    alert_embed.add_field(name="Dedicated Workroom", value=incident_channel.mention, inline=False)
                    alert_embed.set_footer(text="Launch Pixel Emergency Core • Edge AI Scanning")

                    # Raise in current chat where it happened
                    await message.channel.send(content=f"🚨 {ping_str}**A critical incident has been brought up, please look into this!**", embed=alert_embed)

                    # Raise in #blocker-resolution
                    blockers_channel = discord.utils.find(lambda c: c.name.lower() == "blocker-resolution" or c.name.lower() == "testing-chat", message.guild.text_channels)
                    if blockers_channel:
                        await blockers_channel.send(content=f"🚨 **Emergency Alert:**", embed=alert_embed)

                    # Raise in #ticket-activity-feed
                    activity_channel = discord.utils.find(lambda c: c.name.lower() == "ticket-activity-feed", message.guild.text_channels)
                    if activity_channel:
                        await activity_channel.send(f"🔥 **INCIDENT CREATED:** `{ticket_id}`: *{title}* (Logged automatically from chat scanning)")

                    # Send welcome message inside the newly spawned incident channel
                    welcome_embed = discord.Embed(
                        title=f"🔥 {ticket_id}: Incident Response Room",
                        description=(
                            f"This channel has been **automatically spawned** to resolve a critical emergency.\n\n"
                            f"**Outage/Emergency Summary:**\n{summary}\n\n"
                            f"**Reported by:** {message.author.display_name} inside #{message.channel.name}\n\n"
                            f"**Hotfix checklist:**\n"
                            f"1. Identify the root cause of the error.\n"
                            f"2. Apply a hotfix to restore services.\n"
                            f"3. Verify everything is stable.\n"
                            f"4. Run `!ticket status {ticket_id} Closed` to archive this workspace."
                        ),
                        color=0xE74C3C
                    )
                    await incident_channel.send(content=f"{ping_str}**Emergency Response Team Active!**", embed=welcome_embed)

            except Exception as e:
                print(f"⚠️ Failed to scan for incidents: {e}")

async def alert_scrum_admin(guild, ticket, developer, blocker_details):
    """Pings administrators in #blocker-resolution when a developer is flagged as stuck."""
    # Find blockers channel
    blockers_channel = discord.utils.find(lambda c: c.name.lower() == "blocker-resolution" or c.name.lower() == "testing-chat", guild.text_channels)
    
    # Also find PM or CEO role to ping if they exist
    founder_role = discord.utils.get(guild.roles, name="👑 Founder / CEO")
    pm_role = discord.utils.get(guild.roles, name="📋 Product Manager (Scrum Master)")
    
    ping_str = ""
    if founder_role:
        ping_str += f"{founder_role.mention} "
    if pm_role:
        ping_str += f"{pm_role.mention} "
        
    if blockers_channel:
        admin_embed = discord.Embed(
            title="🚨 DEVELOPER BLOCKED ALERT!",
            description=(
                f"**Developer:** {developer.mention} ({developer.display_name})\n"
                f"**Ticket ID:** `{ticket['id']}`\n"
                f"**Task Title:** {ticket['title']}\n"
                f"**Workspace:** <#{ticket['channel_id']}>\n\n"
                f"🔴 **Blocker Summary:**\n*{blocker_details}*"
            ),
            color=0xE74C3C,
            timestamp=datetime.now()
        )
        await blockers_channel.send(content=f"⚠️ {ping_str}**Blocker logged!**", embed=admin_embed)

# ================= SCRUM MASTER COMMANDS =================

@bot.command(name='scrumcheck')
@commands.has_permissions(manage_channels=True)
async def scrumcheck(ctx):
    """Manually triggers a check-in sweep across all active developer channels."""
    await ctx.send("🕵️‍♂️ Starting manual AI Scrum Check-In sweep...")
    await run_scrum_check_sweep(ctx)

@bot.command(name='stuck')
async def stuck(ctx, *, details: str):
    """Allows a developer to manually flag themselves as stuck, instantly alerting the admin."""
    # Verify this is a ticket channel
    active_tickets = db.get_active_tickets()
    current_ticket = None
    for t in active_tickets:
        if t["channel_id"] == ctx.channel.id:
            current_ticket = t
            break

    if not current_ticket:
        await ctx.send("❌ This command must be used inside a dedicated ticket discussion channel!")
        return

    ticket_id = current_ticket["id"]
    db.add_comment(ticket_id, ctx.author.id, ctx.author.display_name, f"[Blocked/Stuck] {details}")
    
    # Alert admin
    await alert_scrum_admin(ctx.guild, current_ticket, ctx.author, details)
    
    embed = discord.Embed(
        title="🚨 Blocker Manually Flagged",
        description=(
            f"I have successfully logged this blocker to Neon and sent an high-priority alert to the managers.\n\n"
            f"**Your Blocker Notes:**\n*{details}*"
        ),
        color=0xE74C3C
    )
    await ctx.send(embed=embed)

@bot.command(name='help')
async def custom_help(ctx):
    """Help description of the AI Scrum Master Bot."""
    embed = discord.Embed(
        title="🕵️‍♂️ AI Scrum Master Bot Commands (Prefix '?')",
        description="This bot monitors your tickets, tracks updates, logs comments/attachments, and raises red flags when you're stuck.",
        color=0x9B5DE5
    )
    embed.add_field(name="⚙️ Trigger Check-in", value="`?scrumcheck` (PM/Admin only) - Pings all active workspaces for developer updates.", inline=False)
    embed.add_field(name="🚨 Flag Blocker", value="`?stuck <description>` - Manually flags a blocker, logging it to the DB and alerting managers.", inline=False)
    embed.add_field(name="💬 Chat Monitoring", value="Any message you write in ticket workspaces automatically records comments. Sending links or uploading images registers them as attachments on the ticket!", inline=False)
    await ctx.send(embed=embed)

# Start bot
if SCRUM_BOT_TOKEN and SCRUM_BOT_TOKEN != 'your_scrum_bot_token_here':
    try:
        bot.run(SCRUM_BOT_TOKEN)
    except Exception as e:
        print(f"❌ Failed to run Scrum Bot: {e}")
else:
    print("⚠️ [Scrum Bot] 'SCRUM_BOT_TOKEN' not set or default placeholder in .env. Scrum Master Bot will not start.")
