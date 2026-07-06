# Claude Handshake: Launch Pixel ScrumBot

Hello Claude! 👋 I am Antigravity, the AI agent handling the **infrastructure and deployment** side of this project. The user and I have agreed to split the work: I will continue focusing on deployment, environment variables, and cloud hosting (Render), while you take over the **codebase enhancement and feature development**.

## 🚀 Current Project Status
- **Discord Bot**: Successfully boots and connects to the server, deployed to Render.
- **Autonomous Loop**: I just added a new `_autonomous_loop` in `main.py`! The bot will now wake up at random intervals between 1 and 14 minutes, completely replacing the need for cron jobs. It proactively checks GitHub, tracks finances, and reports to Discord if it finds something noteworthy!
- **Core Agent Engine**: I switched the default agent back to `gemini-2.5-flash` for flawless LangChain tool calling, since NVIDIA NIM Llama 3.1 70b was strictly demanding prompt formatting and failing when given blank commands.

## 🛠️ Your Focus Areas (The Code)
The user wants you to look at the codebase and enhance the Scrum Master's intelligence! Here are some immediate areas that need your attention:

1. **The Autonomous Loop Prompt**:
   - Check `main.py` -> `_autonomous_loop()`. The prompt I gave the agent is a bit generic ("track finances, find leads, etc"). 
   - Please refine this prompt or enhance the `ScrumAgent` logic so the bot can actually be "smart", use its memory system effectively, and actually act like a 24/7 asynchronous worker.

2. **Missing Integrations (`launchpixel_cog.py`)**: 
   - I safely **commented out** some broken imports (`whatsapp_webhook` and `gmail_sync`) previously. 
   - **Your Task**: Implement these missing modules (WhatsApp syncing and Gmail polling) or rewrite the integrations to fit the current architecture.

3. **Feature Enhancements**: 
   - Enhance the AI Scrum Master logic and how it interacts with the Composio Tools.
   - Improve the `/blocker` command and email summarization prompts.

## 🤝 How We Will Collaborate
- **You (Claude)**: Write the code, add new features, refactor the python files, and push commits.
- **Me (Antigravity)**: If your changes require new environment variables, changes to `requirements.txt` that affect the Render build, or anything related to the cloud infrastructure, leave a note in this file or have the user tell me, and I will handle the deployment side!

Ready when you are! 
— *Antigravity*
