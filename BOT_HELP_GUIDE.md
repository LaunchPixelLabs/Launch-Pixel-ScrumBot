# 🤖 Launch Pixel DevOps Bot - Command & Help Guide

Welcome to the **Launch Pixel automated Scrum & DevOps system**! This system is backed by a serverless **Neon PostgreSQL database** and runs its webhook routing on **Cloudflare Workers**.

---

## ⚡ 1. Server Setup Automation (`!`)
Run this command once to build your entire operations workspace instantly:

| Command | Usage | Description |
| :--- | :--- | :--- |
| **`!setup_server`** | `!setup_server` | Constructs roles in hierarchy (`Founder`, `PM`, `Dev`, `Designer`, `QA`), creates categories (`WORKSPACE`, `INFO`, `DEVOPS`, `ACTIVE TICKETS`, `ARCHIVED TICKETS`), and initializes the Forum-based `#kanban-board`. |

---

## 🎫 2. JIRA/DevOps Ticketing System (`!`)
Manage your team roadmap, story points, and timelines through the full web board, with Discord forum cards kept in sync.

### 🗂️ Azure-style Board (`/`)
* **`/devops`**: Sends you a private link to the full LaunchPixel DevOps board with drag/drop lanes, filters, create/edit forms, story points, due dates, labels, and Discord thread links.
* **`/board`**: Shows a rich board snapshot grouped by `New`, `Planned`, `Refining`, `Active`, `Reviewing`, and `Blocked`.
* **`/board_publish`**: Run this once inside the text channel that should hold the Discord mirror. LP_Bot creates one live dashboard header plus one live lane message per board column and refreshes them after card changes.
* **`/ticket_new` / `/ticket_move` / `/ticket_view`**: Slash-command work-item management with forum cards and move dropdowns.

### 🆕 Create Ticket
* **Syntax**: `!ticket create Title | Description | [Assignee] | [Priority] | [Story Points] | [Days] | [Start Date] | [End Date] | [Acceptance Criteria]`
* **Example**:
  ```text
  !ticket create Build Login Page | Implement OAuth auth | @username | High | 3 | 5 | 2026-05-25 | 2026-05-30 | User must see error indicators, Passwords must be hashed, Responsive layout
  ```
* **System Action**: 
  1. Assigns a unique JIRA-style ID (`LP-1`, `LP-2`, etc.).
  2. Spins up a dedicated text channel in your sidebar named `#lp-ticket-X-build-login-page` for workspace isolation.
  3. Inserts all fields securely into **Neon serverless PostgreSQL**.
  4. Generates an applied-tag post in your `#kanban-board` forum.

### 👤 Delegate Task
* **Syntax**: `!ticket assign <ID> <@Member>`
* **Example**: `!ticket assign LP-1 @SeniorDev`
* **System Action**: Updates the ticket record in Neon, pings the assignee inside their active workspace room, and updates the channel's description.

### 🔄 Shift Status
* **Syntax**: `!ticket status <ID> <New/Planned/Refining/Active/Reviewing/Blocked/Closed>`
* **Example**: `!ticket status LP-1 Active`
* **System Action**: Shuffles the tags of the card inside the `#kanban-board` forum.
* **🔒 Smart Auto-Archive**: Shifting status to `Closed` automatically moves the workspace channel down to the `📁 ARCHIVED TICKETS` category and revokes write permissions (making it read-only), keeping your server clean while preserving historical chat records!

### 📋 Board Overview
* **Syntax**: `!ticket list`
* **System Action**: Queries Neon SQL and displays a stunning, color-coded embed of all open tasks, assignees, story points, priorities, and workspace links.

### 🔍 Search details
* **Syntax**: `!ticket view <ID>`
* **Example**: `!ticket view LP-1`
* **System Action**: Displays a detailed JIRA dashboard embed. **It pulls and renders all acceptance criteria, plus lists recent discussion logs and downloadable links to file/image attachments uploaded to that channel, queried directly from Neon PostgreSQL!**

---

## 🚀 3. Daily Scrum Standups & AI Blockers (`!`)
Tools to optimize your daily sync-ups:

| Command | Usage | Description |
| :--- | :--- | :--- |
| **`!standup`** | `!standup` | Initiates a daily check-in prompt and automatically opens a dedicated thread labeled with today's date for updates. |
| **`!blocker`** | `!blocker <description>` | Feeds your coding/design blocker to the **Gemini AI Scrum Master** and outputs practical, structured, expert advice to get you unblocked. |

---

## 🕵️‍♂️ 4. AI Scrum Master Bot (Prefix `?`)
Once you connect a second Discord Bot token (`SCRUM_BOT_TOKEN`), it runs silent check-ins:
* **Chat Logging**: Logs every text message inside `#lp-ticket-X` channels to Neon comments.
* **Attachment Logging**: Detects when you upload images/files or paste external links inside workspaces, logging them automatically to Neon PostgreSQL.
* **AI Stuck Scans (Gemini)**: Reads your workspace chat messages. If the AI detects that a developer is stuck, **it triggers a high-priority alert card in `#blockers` and pings Founder and PM roles immediately!**
* **`?stuck <details>`**: Developer command to manually raise a blocker alarm and ping managers.
* **`?scrumcheck`**: Manual sweeps to trigger check-ins on all active workspaces.
