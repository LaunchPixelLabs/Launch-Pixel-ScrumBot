// Registers LP_Bot's global slash commands with Discord.
//
//   DISCORD_TOKEN=... APPLICATION_ID=1508225212133412995 node scripts/register-commands.mjs
//
// Global commands can take up to ~1 hour to propagate. To test instantly, set
// GUILD_ID=<your server id> and they register for that guild immediately.
import fs from "node:fs";

function loadDotEnv(path) {
  if (!fs.existsSync(path)) return;
  for (const line of fs.readFileSync(path, "utf8").split(/\r?\n/)) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*=/.test(line)) continue;
    const i = line.indexOf("=");
    const key = line.slice(0, i);
    const value = line.slice(i + 1).trim().replace(/^(['"])(.*)\1$/, "$2");
    if (!process.env[key]) process.env[key] = value;
  }
}

loadDotEnv("../.env");
loadDotEnv(".env");

const TOKEN = process.env.DISCORD_TOKEN;
const APP_ID = process.env.APPLICATION_ID || "1508225212133412995";
const GUILD_ID = process.env.GUILD_ID;

if (!TOKEN) {
  console.error("Missing DISCORD_TOKEN env var.");
  process.exit(1);
}

const COLUMN_CHOICES = [
  { name: "New", value: "New" },
  { name: "Planned", value: "Planned" },
  { name: "Refining", value: "Refining" },
  { name: "Active", value: "Active" },
  { name: "Reviewing", value: "Reviewing" },
  { name: "Blocked", value: "Blocked" },
  { name: "Closed", value: "Closed" },
];
const PRIORITY_CHOICES = [
  { name: "Low", value: "Low" },
  { name: "Medium", value: "Medium" },
  { name: "High", value: "High" },
  { name: "Critical", value: "Critical" },
];

const COMMANDS = [
  { name: "ask", description: "Ask LP_Bot anything — it uses tools + memory to answer and act.", options: [{ name: "query", description: "Your question or instruction", type: 3, required: true }] },
  { name: "board", description: "Overview of the current board (tickets by status)." },
  { name: "devops", description: "Open the full Azure-style LaunchPixel DevOps board." },
  { name: "board_publish", description: "Create or refresh the persistent Azure-style DevOps board in this channel." },
  { name: "board_sync", description: "Backfill board cards and refresh the DevOps dashboard." },
  { name: "standup", description: "Generate today's standup summary from board activity." },
  { name: "leads", description: "Summarise the sales lead pipeline." },
  { name: "finance", description: "Summarise recent spend and burn." },
  { name: "business", description: "Ask the Business Brain about SOPs, KPIs, strategy.", options: [{ name: "query", description: "Business question", type: 3, required: true }] },
  { name: "briefing", description: "Founder-ready morning briefing across the whole business." },
  { name: "status", description: "Short live status-of-the-business snapshot." },
  { name: "decisions", description: "List recent Dual-Brain council decisions." },
  { name: "council", description: "Put a high-stakes decision to BOTH brains for a weighted verdict.", options: [{ name: "decision", description: "The decision to deliberate", type: 3, required: true }] },
  { name: "learn", description: "Teach LP_Bot a business rule / SOP / KPI.", options: [{ name: "topic", description: "Short title", type: 3, required: true }, { name: "content", description: "The rule", type: 3, required: true }] },
  { name: "ticket_new", description: "Create a new card on the kanban board.", options: [
    { name: "title", description: "Ticket title", type: 3, required: true },
    { name: "description", description: "Details", type: 3, required: false },
    { name: "assignee", description: "Who owns it", type: 3, required: false },
    { name: "priority", description: "Priority", type: 3, required: false, choices: PRIORITY_CHOICES },
    { name: "story_points", description: "Story points", type: 4, required: false },
    { name: "due_date", description: "Due date as YYYY-MM-DD", type: 3, required: false },
    { name: "labels", description: "Comma-separated tags/labels", type: 3, required: false },
    { name: "status", description: "Starting column (default New)", type: 3, required: false, choices: COLUMN_CHOICES },
  ] },
  { name: "ticket_move", description: "Move a card to another column on the board.", options: [
    { name: "id", description: "Ticket id (e.g. LP-XXXX)", type: 3, required: true },
    { name: "status", description: "Destination column", type: 3, required: true, choices: COLUMN_CHOICES },
  ] },
  { name: "ticket_view", description: "Open a rich DevOps work-item view for a card.", options: [
    { name: "id", description: "Ticket id (e.g. LP-XXXX)", type: 3, required: true },
  ] },
];

const url = GUILD_ID
  ? `https://discord.com/api/v10/applications/${APP_ID}/guilds/${GUILD_ID}/commands`
  : `https://discord.com/api/v10/applications/${APP_ID}/commands`;

const res = await fetch(url, {
  method: "PUT",
  headers: { "Content-Type": "application/json", Authorization: `Bot ${TOKEN}` },
  body: JSON.stringify(COMMANDS),
});

if (res.ok) {
  const data = await res.json();
  console.log(`✅ Registered ${data.length} commands ${GUILD_ID ? "to guild " + GUILD_ID : "globally"}.`);
} else {
  console.error(`❌ Failed (${res.status}):`, await res.text());
  process.exit(1);
}
