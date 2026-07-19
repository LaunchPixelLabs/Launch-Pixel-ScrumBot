// Discord transport: chunking, deferred-interaction follow-ups, channel posts,
// DMs, and the slash-command catalogue used by the registration script.
import { Env } from "./types";
import { COLUMNS } from "./board";

const API = "https://discord.com/api/v10";

export interface DiscordMessagePayload {
  content?: string;
  embeds?: any[];
  components?: any[];
  flags?: number;
  allowed_mentions?: any;
}

export type DiscordReply = string | DiscordMessagePayload;

export function chunk(text: string, size = 1990): string[] {
  text = (text || "(no response)").toString();
  if (text.length <= size) return [text];
  const out: string[] = [];
  let cur = "";
  for (const line of text.split(/(?<=\n)/)) {
    if (cur.length + line.length > size) {
      if (cur) out.push(cur), (cur = "");
      let l = line;
      while (l.length > size) {
        out.push(l.slice(0, size));
        l = l.slice(size);
      }
      cur = l;
    } else cur += line;
  }
  if (cur) out.push(cur);
  return out;
}

/** Edit the deferred interaction's original message, then send any overflow as
 *  follow-up messages. Uses the interaction token (no bot auth needed). */
export async function editInteraction(env: Env, token: string, reply: DiscordReply): Promise<void> {
  const payload: DiscordMessagePayload = typeof reply === "string" ? { content: reply } : reply;
  const content = payload.content;
  const parts = typeof content === "string" && content.length > 1990 ? chunk(content) : [];
  const app = env.APPLICATION_ID;
  await fetch(`${API}/webhooks/${app}/${token}/messages/@original`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parts.length ? { ...payload, content: parts[0] } : payload),
  });
  for (let i = 1; i < parts.length; i++) {
    await fetch(`${API}/webhooks/${app}/${token}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: parts[i] }),
    });
  }
}

/** Post a message to a channel as the bot (used by the autonomous loop). */
export async function postToChannel(env: Env, channelId: string, content: string): Promise<void> {
  for (const part of chunk(content)) {
    await fetch(`${API}/channels/${channelId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bot ${env.DISCORD_TOKEN}` },
      body: JSON.stringify({ content: part }),
    });
  }
}

export async function postPayloadToChannel(env: Env, channelId: string, payload: DiscordMessagePayload): Promise<any | null> {
  const res = await fetch(`${API}/channels/${channelId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bot ${env.DISCORD_TOKEN}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.error("postPayloadToChannel failed:", res.status, await res.text());
    return null;
  }
  return res.json();
}

export async function editChannelMessage(env: Env, channelId: string, messageId: string, payload: DiscordMessagePayload): Promise<any | null> {
  const res = await fetch(`${API}/channels/${channelId}/messages/${messageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bot ${env.DISCORD_TOKEN}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.error("editChannelMessage failed:", res.status, await res.text());
    return null;
  }
  return res.json();
}

/** DM a user (opens a DM channel first). Best-effort. */
export async function dmUser(env: Env, userId: string, content: string): Promise<void> {
  try {
    const res = await fetch(`${API}/users/@me/channels`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bot ${env.DISCORD_TOKEN}` },
      body: JSON.stringify({ recipient_id: userId }),
    });
    const dm: any = await res.json();
    if (dm?.id) await postToChannel(env, dm.id, content);
  } catch (e) {
    console.error("dmUser failed:", e);
  }
}

// Board columns and priorities, offered as slash-command choices so the founder
// picks from a menu instead of free-typing (and mistyping) a status.
const COLUMN_CHOICES = COLUMNS.map((c) => ({ name: c, value: c }));
const PRIORITY_CHOICES = [
  { name: "Low", value: "Low" },
  { name: "Medium", value: "Medium" },
  { name: "High", value: "High" },
  { name: "Critical", value: "Critical" },
];

// Option types: 1=SUB_COMMAND 3=STRING 4=INTEGER
export const COMMANDS = [
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
