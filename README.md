<div align="center">
  <img src="https://launchpixel.in/animated-logo.gif" width="200" alt="LaunchPixel Logo" />
  <h1>🚀 LaunchPixel ScrumBot</h1>
  <p><strong>An Elite, AI-Powered Agile Scrum Master for Discord</strong></p>
</div>

---

## 🌟 Overview

**LP-ScrumBot** is a high-performance, serverless Discord bot designed to act as an independent, senior-level Agile Scrum Master for the LaunchPixel team. 

Powered by **LangChain**, **Groq (Llama-3)**, and **Cloudflare Workers**, this bot facilitates daily standups, analyzes sprint estimates, and dynamically fetches live DevOps backlog data directly from the internal `admins.launchpixel.in` portal. It features long-term conversational memory using **NeonDB**, ensuring it never forgets past discussions, blockers, or team dynamics!

## ✨ Key Features

- ⚡ **Zero-Latency Edge Network:** Hosted on Cloudflare Workers using HTTP Interactions (0ms cold start, 24/7 uptime).
- 🧠 **Persistent Memory:** Remembers conversations across stateless requests using NeonDB Serverless Postgres.
- 🔗 **Live Backlog Integration:** Integrates seamlessly with LaunchPixel's custom admin portal to fetch Epics, Features, and Tasks.
- 🎯 **Senior Persona:** Expertly challenges team blockers, manages backlog grooming, and facilitates standups like a seasoned pro.
- 🔄 **Automated CI/CD:** Fully configured GitHub Actions pipeline for instant, seamless deployments on push.

## 🛠️ Architecture

- **Transport:** Cloudflare Workers (Hono.js) handling Discord HTTP Interaction Webhooks.
- **Orchestration:** LangChain for intent routing and AI memory management.
- **Database:** NeonDB Serverless Postgres (via Drizzle ORM).
- **LLM:** Groq / NVIDIA NIM (defaulting to highly-capable open models).

---

## 🚀 Setup & Installation (Missing Configuration)

This repository contains the full source code, but for security, sensitive API keys and connection URLs have been omitted. To run this bot yourself or deploy it to production, follow these steps:

### 1. Cloudflare Secret Configuration
You must inject the following secure variables into your Cloudflare Worker environment using the Wrangler CLI (`npx wrangler secret put <KEY>`):

| Secret Key | Description |
|---|---|
| `DISCORD_PUBLIC_KEY` | The Public Key from your Discord Developer Portal application. |
| `DATABASE_URL` | Your NeonDB Postgres connection string. |
| `LLM_API_KEY` | Your Groq or NVIDIA NIM API Key. |
| `LLM_BASE_URL` | The base URL for your LLM provider (e.g., `https://api.groq.com/openai/v1`). |
| `LP_PORTAL_BASE_URL` | The API URL for your project management backend (e.g., `https://api.yourcompany.com`). |
| `LP_PORTAL_API_KEY` | The secure `x-api-key` required to authenticate with the backend. |

*(Note: Never commit these keys to version control!)*

### 2. Database Schema Push
Before the bot can remember conversations, you must push the Drizzle schema to your Neon database:
```bash
npx drizzle-kit push:pg
```

### 3. Connect to Discord
Go to the Discord Developer Portal, find your Bot application, and paste your deployed Cloudflare URL into the **Interactions Endpoint URL** field (make sure to append `/api/interactions` to the end of the URL).

### 4. Seamless CI/CD Push (GitHub Actions)
To enable automatic deployments when pushing to the `main` branch:
1. Generate a Cloudflare API Token (with Edit Worker permissions).
2. Add the token to your GitHub Repository Secrets as `CLOUDFLARE_API_TOKEN`.

---
<div align="center">
  <p>Built with ❤️ by the <strong>LaunchPixel Team</strong></p>
</div>
