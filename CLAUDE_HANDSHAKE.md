# Claude Handshake: Launch Pixel ScrumBot

Hello Claude! 👋 I am Antigravity, the AI agent handling the **infrastructure and deployment** side of this project. The user and I have agreed to split the work: I will continue focusing on deployment, environment variables, and cloud hosting (Render), while you take over the **codebase enhancement and feature development**.

## 🚀 Current Project Status
- **Discord Bot**: Successfully boots and connects to the server.
- **Hosting**: Deployed on Render. We recently fixed some deployment crash loops caused by missing dependencies (`arxiv`, `wikipedia`, `duckduckgo-search`).
- **Recent Fixes**: I just repaired a fatal `IndentationError` in `scrumbot/discord/launchpixel_cog.py` that was crashing the bot during startup.

## 🛠️ Your Focus Areas (The Code)
The user wants you to look at the codebase and enhance it. Here are some immediate areas that need your attention:

1. **Missing Integrations (`launchpixel_cog.py`)**: 
   - The user recently pasted some custom Cog code, but it relies on two modules that do not exist in this repository: `whatsapp_webhook` and `gmail_sync`.
   - I have safely **commented out** these imports and the broken logic at the bottom of `scrumbot/discord/launchpixel_cog.py` so the bot could boot. 
   - **Your Task**: Implement these missing modules (WhatsApp syncing and Gmail polling) or rewrite the integrations to fit the current architecture.

2. **Codebase Cleanup**: 
   - Review `launchpixel_cog.py` and the general bot structure. The recent pasted code introduced some floating global variables (which I removed) and mangled indentation. 
   - Please ensure the `discord.py` cogs are structured following best practices.

3. **Feature Enhancements**: 
   - Enhance the AI Scrum Master logic (which uses the Gemini API).
   - Improve the `/blocker` command and email summarization prompts.

## 🤝 How We Will Collaborate
- **You (Claude)**: Write the code, add new features, refactor the python files, and push commits.
- **Me (Antigravity)**: If your changes require new environment variables, changes to `requirements.txt` that affect the Render build, or anything related to the cloud infrastructure, leave a note in this file or have the user tell me, and I will handle the deployment side!

Ready when you are! 
— *Antigravity*
