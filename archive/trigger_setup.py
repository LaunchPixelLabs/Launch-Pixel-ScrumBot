import os
import discord
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.guilds = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"🟢 [Automation] Logged in as {client.user.name} to trigger server setup!")
    
    if not client.guilds:
        print("❌ [Error] The bot is not in any server! Please invite the bot to your server first.")
        await client.close()
        return
        
    guild = client.guilds[0]
    print(f"⚡ [Automation] Targeting Discord Server: {guild.name} (ID: {guild.id})")
    
    # 1. Create Roles
    roles_config = [
        {"name": "👑 Founder / CEO", "color": 0xD4AF37},
        {"name": "📋 Product Manager (Scrum Master)", "color": 0x9B5DE5},
        {"name": "💻 Senior Dev", "color": 0x00F5D4},
        {"name": "🎨 UI/UX Designer", "color": 0xF15BB5},
        {"name": "🧪 QA Tester", "color": 0x2ECC71}
    ]
    
    for rc in roles_config:
        try:
            role = discord.utils.get(guild.roles, name=rc["name"])
            if not role:
                role = await guild.create_role(
                    name=rc["name"],
                    color=discord.Color(rc["color"]),
                    hoist=True,
                    mentionable=True
                )
                print(f"   ↳ Created role: {role.name}")
            else:
                print(f"   ↳ Role exists: {role.name}")
        except discord.errors.Forbidden:
            print(f"   ⚠️ [Permission Denied] Lacking permission to manage roles. Skipping role: {rc['name']}")
            
    # 2. Create Categories & Channels
    categories = {
        "📢 INFO & STATS": [
            {"name": "welcome-rules", "type": "text"},
            {"name": "announcements", "type": "text"},
            {"name": "scrum-dashboard", "type": "text"},
            {"name": "🔊 Town Hall", "type": "voice"}
        ],
        "General General": [
            {"name": "general", "type": "text"},
            {"name": "random-chill", "type": "text"},
            {"name": "🔊 General Voice", "type": "voice"},
            {"name": "🔊 Co-Working Lounge", "type": "voice"}
        ],
        "💻 ENGINEERING (DEV)": [
            {"name": "dev-chat", "type": "text"},
            {"name": "dev-issues", "type": "text"},
            {"name": "🔊 Dev Standup", "type": "voice"},
            {"name": "🔊 Pair Programming 1", "type": "voice"},
            {"name": "🔊 Pair Programming 2", "type": "voice"}
        ],
        "🎨 UI UX DESIGN": [
            {"name": "design-chat", "type": "text"},
            {"name": "design-feedback", "type": "text"},
            {"name": "🔊 Design Review", "type": "voice"}
        ],
        "🧪 QA & TESTING": [
            {"name": "testing-logs", "type": "text"},
            {"name": "bug-reports", "type": "text"},
            {"name": "🔊 QA Review", "type": "voice"}
        ],
        "🤖 SCRUM & ALERTS": [
            {"name": "standups", "type": "text"},
            {"name": "blockers", "type": "text"},
            {"name": "client-emails", "type": "text"},
            {"name": "whatsapp-sync", "type": "text"}
        ],
        "📋 DEVOPS (JIRA)": [
            {"name": "tickets-activity", "type": "text"}
        ],
        "🎫 ACTIVE TICKETS": [],
        "📁 ARCHIVED TICKETS": []
    }
    
    for cat_name, channels in categories.items():
        category = discord.utils.get(guild.categories, name=cat_name)
        if not category:
            category = await guild.create_category(name=cat_name)
            print(f"🔹 Created Category: {cat_name}")
            
        for ch in channels:
            ch_name = ch["name"]
            ch_type = ch["type"]
            
            if ch_type == "text":
                existing = discord.utils.find(lambda c: c.name.lower() == ch_name.lower() and c.category == category and isinstance(c, discord.TextChannel), guild.channels)
                if not existing:
                    await guild.create_text_channel(name=ch_name, category=category)
                    print(f"   ↳ Created Text Channel: #{ch_name}")
            elif ch_type == "voice":
                existing = discord.utils.find(lambda c: c.name.lower() == ch_name.lower() and c.category == category and isinstance(c, discord.VoiceChannel), guild.channels)
                if not existing:
                    await guild.create_voice_channel(name=ch_name, category=category)
                    print(f"   ↳ Created Voice Channel: 🔊 {ch_name}")
                    
        if cat_name == "📋 DEVOPS (JIRA)":
            forum_ch = discord.utils.find(lambda c: c.name.lower() == "kanban-board" and c.category == category, guild.channels)
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
                    await guild.create_forum(
                        name="kanban-board",
                        category=category,
                        available_tags=tags,
                        topic="Project Kanban Board - Create tasks using !ticket create!"
                    )
                    print("   ↳ Created Forum Kanban Board successfully!")
                except Exception as e:
                    print(f"   ⚠️ Could not create forum channel (Forum requires Community Features enabled): {e}")

    print("🎉 [Automation] Live server setup completed successfully! Shutting down script...")
    await client.close()

client.run(DISCORD_TOKEN)
