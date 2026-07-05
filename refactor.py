import sys
import re

with open('scrumbot/discord/launchpixel_cog.py', 'r') as f:
    content = f.read()

# Replace global bot.command and bot.event with cog decorators
content = content.replace("@bot.command", "@commands.command")
content = content.replace("@bot.group", "@commands.group")
content = content.replace("@bot.event", "@commands.Cog.listener()")

# Wrap in a cog class
lines = content.split('\n')
new_lines = [
    "import discord",
    "from discord.ext import commands, tasks",
    "import os",
    "import json",
    "import asyncio",
    "import threading",
    "from datetime import datetime",
    "from dotenv import load_dotenv",
    "from google import genai",
    "import db",
    "import whatsapp_webhook",
    "from gmail_sync import GmailSync",
    "",
    "class LaunchPixelCog(commands.Cog):",
    "    def __init__(self, bot):",
    "        self.bot = bot",
    "        self.gemini_client = None",
    "        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')",
    "        if GEMINI_API_KEY and GEMINI_API_KEY != 'your_gemini_api_key_here':",
    "            try:",
    "                self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)",
    "            except Exception as e:",
    "                print(f'Failed to initialize Gemini: {e}')",
    "        self.gmail_client_sync = GmailSync()",
    "        # Initialize tasks",
    "        self.poll_gmail.start()",
    ""
]

# We need to indent all functions that have @commands decorators and pass self.
inside_class_methods = False
for line in lines:
    if line.startswith("import") or line.startswith("from"):
        continue
    if line.startswith("load_dotenv()"):
        continue
    if line.startswith("DISCORD_TOKEN"):
        continue
    if line.startswith("GEMINI_API_KEY"):
        continue
    if line.startswith("intents ="):
        continue
    if line.startswith("bot ="):
        continue
    if line.startswith("bot.remove_command"):
        continue
    if line.startswith("gemini_client ="):
        continue
    if line.startswith("gmail_client_sync ="):
        continue
    if line.startswith("if GEMINI_API_KEY") or line.startswith("    try:") or line.startswith("    except Exception"):
        # We already handled gemini setup
        continue
    if line.startswith("        gemini_client = genai.Client"):
        continue
    if line.startswith("        print(f\"Failed"):
        continue
        
    # Replace global references
    line = line.replace("bot.guilds", "self.bot.guilds")
    line = line.replace("bot.change_presence", "self.bot.change_presence")
    line = line.replace("bot.add_view", "self.bot.add_view")
    line = line.replace("gemini_client", "self.gemini_client")
    line = line.replace("gmail_client_sync", "self.gmail_client_sync")
    line = line.replace("bot.loop", "self.bot.loop")
    
    # Check if we are defining a function that should be a method
    if line.startswith("async def ") or line.startswith("def "):
        if line.startswith("def load_tickets"):
            new_lines.append(line)
        elif line.startswith("def save_tickets"):
            new_lines.append(line)
        elif line.startswith("def handle_whatsapp_message"):
            new_lines.append(line)
        elif line.startswith("def start_webhook_server"):
            new_lines.append(line)
        elif line.startswith("async def post_whatsapp"):
            new_lines.append(line)
        else:
            # It's a command/listener
            line = line.replace("(ctx", "(self, ctx").replace("()", "(self)")
            new_lines.append("    " + line)
            inside_class_methods = True
    elif line.startswith("@commands") or line.startswith("@tasks"):
        new_lines.append("    " + line)
    elif line.startswith("@setup_server.error"):
        new_lines.append("    " + line)
    elif inside_class_methods and (line.startswith(" ") or line == ""):
        new_lines.append("    " + line)
    elif not inside_class_methods:
        new_lines.append(line)
    elif line.startswith("whatsapp_webhook.") or line.startswith("webhook_thread") or line.startswith("bot.run"):
        pass
    else:
        new_lines.append("    " + line)

with open('scrumbot/discord/launchpixel_cog.py', 'w') as f:
    f.write('\n'.join(new_lines))

