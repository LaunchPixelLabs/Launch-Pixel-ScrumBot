// Native Discord Forum kanban engine.
//
// The #kanban-board channel is a Discord forum channel whose tags are the board
// columns. One ticket == one forum post (thread); the applied tag == the column.
// Discord cannot render a true Azure DevOps board inside a normal message, so we
// use its closest native model: forum tags for lanes, rich post cards, and a move
// dropdown on each card.
import { Env } from "./types";

const API = "https://discord.com/api/v10";

// --- Canonical columns (must match the forum's tag names) ------------------
// Order matters: this is the left-to-right column order on the board.
export const COLUMNS = ["New", "Planned", "Refining", "Active", "Reviewing", "Blocked", "Closed"] as const;
export type Column = (typeof COLUMNS)[number];
export const ACTIVE_COLUMNS = COLUMNS.filter((c) => c !== "Closed") as Exclude<Column, "Closed">[];

export const COLUMN_EMOJI: Record<Column, string> = {
  New: "🆕",
  Planned: "📅",
  Refining: "🔧",
  Active: "▶️",
  Reviewing: "👀",
  Blocked: "⛔",
  Closed: "📁",
};

export const WIP_LIMITS: Partial<Record<Column, number>> = {
  Planned: 5,
  Refining: 5,
  Active: 5,
  Reviewing: 5,
};

// Loose input -> canonical column. Lets humans type "in progress", "todo", "done"
// and still land in the right lane.
const SYNONYMS: Record<string, Column> = {
  new: "New", todo: "New", "to do": "New", backlog: "New", open: "New", created: "New",
  planned: "Planned", ready: "Planned", next: "Planned", scheduled: "Planned",
  refining: "Refining", refine: "Refining", groom: "Refining", grooming: "Refining", analysis: "Refining",
  active: "Active", "in progress": "Active", "in-progress": "Active", doing: "Active", wip: "Active", started: "Active",
  reviewing: "Reviewing", review: "Reviewing", qa: "Reviewing", testing: "Reviewing", validation: "Reviewing",
  blocked: "Blocked", blocker: "Blocked", stuck: "Blocked", impeded: "Blocked", impediment: "Blocked", waiting: "Blocked",
  resolved: "Closed", done: "Closed", complete: "Closed", completed: "Closed", finished: "Closed", shipped: "Closed",
  closed: "Closed", archived: "Closed", cancelled: "Closed", canceled: "Closed", "won't fix": "Closed", wontfix: "Closed",
};

/** Normalise any status string to a canonical board column (defaults to New). */
export function normalizeColumn(status?: string): Column {
  const key = (status || "").trim().toLowerCase();
  if (!key) return "New";
  if (SYNONYMS[key]) return SYNONYMS[key];
  const hit = COLUMNS.find((c) => c.toLowerCase() === key);
  return hit || SYNONYMS[key] || "New";
}

// --- Card styling ----------------------------------------------------------
export const COLUMN_COLOR: Record<Column, number> = {
  New: 0x868e96,      // slate
  Planned: 0x4c6ef5,  // indigo
  Refining: 0xf08c00, // amber — shaping/spec work
  Active: 0x2f9e44,   // green — work in flight
  Reviewing: 0x0ca678, // teal — review/QA
  Blocked: 0xe03131,  // red — blocked work
  Closed: 0x495057,   // graphite — archived
};

const PRIORITY_BADGE: Record<string, string> = {
  Critical: "🔴 Critical",
  High: "🟠 High",
  Medium: "🟡 Medium",
  Low: "🟢 Low",
};

export interface TicketCard {
  id: string;
  title: string;
  description?: string;
  assignee_name?: string;
  priority?: string;
  status?: string;
  story_points?: number | string | null;
  end_date?: string | Date | null;
  labels?: string | null;
}

const MOVE_CUSTOM_ID_PREFIX = "lp_ticket_move:";

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, Math.max(0, max - 1))}…`;
}

function formatDate(value?: string | Date | null): string {
  if (!value) return "Not set";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  const s = String(value);
  return s.includes("T") ? s.slice(0, 10) : s.slice(0, 20);
}

export function labelList(labels?: string | null): string[] {
  return String(labels || "")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean)
    .slice(0, 6);
}

export function wipLabel(col: Column, count: number): string {
  const limit = WIP_LIMITS[col];
  if (!limit) return String(count);
  return count > limit ? `${count}/${limit} over` : `${count}/${limit}`;
}

export function columnHeading(col: Column, count: number): string {
  return `${COLUMN_EMOJI[col]} ${col} · ${wipLabel(col, count)}`;
}

/** Build the rich embed shown as a kanban card (the forum post's first message). */
export function renderCard(t: TicketCard): any {
  const col = normalizeColumn(t.status);
  const priority = t.priority && PRIORITY_BADGE[t.priority] ? PRIORITY_BADGE[t.priority] : t.priority || "🟡 Medium";
  const points = t.story_points === 0 || t.story_points ? `${t.story_points} SP` : "1 SP";
  const labels = labelList(t.labels);
  const fields: any[] = [
    { name: "State", value: `${COLUMN_EMOJI[col]} \`${col}\``, inline: true },
    { name: "Priority", value: priority, inline: true },
    { name: "Owner", value: t.assignee_name ? t.assignee_name : "_Unassigned_", inline: true },
    { name: "Story Points", value: points, inline: true },
    { name: "Due", value: formatDate(t.end_date), inline: true },
  ];
  if (labels.length) fields.push({ name: "Tags", value: labels.map((l) => `\`${truncate(l, 22)}\``).join(" "), inline: true });
  const desc = (t.description || "").trim();
  return {
    title: truncate(`${t.id} · ${t.title}`, 250),
    description: desc ? truncate(desc, 3200) : "_No description yet._",
    color: COLUMN_COLOR[col],
    fields,
    footer: { text: `LaunchPixel Azure-style Board · ${col}` },
  };
}

/** Move dropdown rendered on each forum card. */
export function renderCardComponents(t: TicketCard): any[] {
  const col = normalizeColumn(t.status);
  return [
    {
      type: 1,
      components: [
        {
          type: 3,
          custom_id: `${MOVE_CUSTOM_ID_PREFIX}${t.id}`.slice(0, 100),
          placeholder: `Move ${t.id} to another lane`,
          min_values: 1,
          max_values: 1,
          options: COLUMNS.map((c) => ({
            label: c,
            value: c,
            description: c === "Closed" ? "Archive completed work" : `Move card to ${c}`,
            emoji: { name: COLUMN_EMOJI[c] },
            default: c === col,
          })),
        },
      ],
    },
  ];
}

export function parseMoveComponent(customId?: string, values?: string[]): { ticketId: string; column: Column } | null {
  if (!customId || !customId.startsWith(MOVE_CUSTOM_ID_PREFIX)) return null;
  const ticketId = customId.slice(MOVE_CUSTOM_ID_PREFIX.length).trim();
  const column = normalizeColumn(values?.[0]);
  return ticketId ? { ticketId, column } : null;
}

// --- Forum tag resolution (cached in KV) -----------------------------------
type TagMap = Record<string, string>; // lowercased tag name -> tag id

const TAG_CACHE_KEY = "kanban:tags";
const TAG_CACHE_TTL = 6 * 60 * 60; // 6h — tags almost never change
const LEGACY_STATUS_TAGS = new Set(["resolved"]);

async function discord(env: Env, path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bot ${env.DISCORD_TOKEN}`,
      ...(init?.headers || {}),
    },
  });
}

function toPatchTag(tag: any): any {
  const out: any = {
    name: truncate(String(tag.name || ""), 20),
    moderated: Boolean(tag.moderated),
  };
  if (tag.id) out.id = String(tag.id);
  if (tag.emoji_id) out.emoji_id = String(tag.emoji_id);
  else if (tag.emoji_name) out.emoji_name = String(tag.emoji_name);
  return out;
}

function mapTags(tags: any[]): TagMap {
  const map: TagMap = {};
  for (const tag of tags || []) {
    if (tag?.name && tag?.id) map[String(tag.name).toLowerCase()] = String(tag.id);
  }
  return map;
}

/** Fetch (and cache) the forum's tag name->id map. Returns {} on failure. */
export async function getTagMap(env: Env, forceRefresh = false): Promise<TagMap> {
  const forum = env.KANBAN_FORUM_CHANNEL_ID;
  if (!forum) return {};
  if (!forceRefresh) {
    try {
      const cached = await env.LP_STATE.get(TAG_CACHE_KEY);
      if (cached) return JSON.parse(cached) as TagMap;
    } catch {
      /* ignore cache miss */
    }
  }
  try {
    const res = await discord(env, `/channels/${forum}`);
    if (!res.ok) {
      console.error("getTagMap: channel fetch failed", res.status, await res.text());
      return {};
    }
    const ch: any = await res.json();
    let tags = ch.available_tags || [];
    let map = mapTags(tags);
    const missing = COLUMNS.filter((col) => !map[col.toLowerCase()]);
    const hasLegacy = tags.some((tag: any) => LEGACY_STATUS_TAGS.has(String(tag?.name || "").toLowerCase()));
    if (missing.length || hasLegacy) {
      const nextTags = [
        ...tags.filter((tag: any) => !LEGACY_STATUS_TAGS.has(String(tag?.name || "").toLowerCase())).map(toPatchTag),
        ...missing.map((col) => ({ name: col, moderated: false, emoji_name: COLUMN_EMOJI[col] })),
      ].slice(0, 20);
      const patched = await discord(env, `/channels/${forum}`, {
        method: "PATCH",
        body: JSON.stringify({ available_tags: nextTags }),
      });
      if (patched.ok) {
        const updated: any = await patched.json();
        tags = updated.available_tags || nextTags;
        map = mapTags(tags);
      } else {
        console.error("getTagMap: tag repair failed", patched.status, await patched.text());
      }
    }
    try {
      await env.LP_STATE.put(TAG_CACHE_KEY, JSON.stringify(map), { expirationTtl: TAG_CACHE_TTL });
    } catch {
      /* KV write is best-effort */
    }
    return map;
  } catch (e: any) {
    console.error("getTagMap error:", e?.message || e);
    return {};
  }
}

/** Resolve a column to its Discord tag id, refreshing the cache once on a miss. */
async function tagIdForColumn(env: Env, col: Column): Promise<string | null> {
  let map = await getTagMap(env);
  let id = map[col.toLowerCase()];
  if (!id) {
    map = await getTagMap(env, true); // maybe the founder just added/renamed the tag
    id = map[col.toLowerCase()];
  }
  return id || null;
}

// --- Public operations -----------------------------------------------------

export interface ForumPostRef {
  thread_id: string;
  // For forum posts the starter message shares the thread's id, so we only need one.
}

/**
 * Create a forum post for a ticket: a new thread named after the ticket, tagged
 * into the right column, with the card embed as its first message.
 * Returns the thread id, or null if the board isn't wired / the call failed.
 */
export async function createForumPost(env: Env, t: TicketCard): Promise<ForumPostRef | null> {
  const forum = env.KANBAN_FORUM_CHANNEL_ID;
  if (!forum) return null;
  const col = normalizeColumn(t.status);
  const tagId = await tagIdForColumn(env, col);
  const body: any = {
    name: `${t.id} · ${t.title}`.slice(0, 100),
    auto_archive_duration: 10080, // 7 days
    applied_tags: tagId ? [tagId] : [],
    message: { embeds: [renderCard({ ...t, status: col })], components: renderCardComponents({ ...t, status: col }) },
  };
  try {
    const res = await discord(env, `/channels/${forum}/threads`, { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) {
      console.error("createForumPost failed:", res.status, await res.text());
      return null;
    }
    const thread: any = await res.json();
    return { thread_id: String(thread.id) };
  } catch (e: any) {
    console.error("createForumPost error:", e?.message || e);
    return null;
  }
}

/**
 * Move an existing ticket's post to a new column: swap the applied tag, refresh
 * the card embed, and drop a short change note in the thread. Best-effort.
 */
export async function moveForumPost(env: Env, threadId: string, t: TicketCard, toColumn: Column, byName?: string): Promise<boolean> {
  if (!env.KANBAN_FORUM_CHANNEL_ID || !threadId) return false;
  const tagId = await tagIdForColumn(env, toColumn);
  let ok = false;
  try {
    // 1) Re-tag + un-archive so a resolved card can move back if needed.
    const patch = await discord(env, `/channels/${threadId}`, {
      method: "PATCH",
      body: JSON.stringify({ applied_tags: tagId ? [tagId] : [], archived: false }),
    });
    ok = patch.ok;
    if (!patch.ok) console.error("moveForumPost re-tag failed:", patch.status, await patch.text());

    // 2) Refresh the starter card embed (starter message id == thread id in forums).
    await discord(env, `/channels/${threadId}/messages/${threadId}`, {
      method: "PATCH",
      body: JSON.stringify({ embeds: [renderCard({ ...t, status: toColumn })], components: renderCardComponents({ ...t, status: toColumn }) }),
    }).catch(() => {});

    // 3) Human-readable audit line in the thread.
    const who = byName ? ` by **${byName}**` : "";
    await discord(env, `/channels/${threadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: `➡️ Moved to **${toColumn}**${who}.` }),
    }).catch(() => {});
  } catch (e: any) {
    console.error("moveForumPost error:", e?.message || e);
  }
  return ok;
}

/** Post a plain comment into a ticket's thread (used for activity / autonomous notes). */
export async function commentOnPost(env: Env, threadId: string, content: string): Promise<void> {
  if (!threadId) return;
  await discord(env, `/channels/${threadId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content: content.slice(0, 1990) }),
  }).catch((e) => console.error("commentOnPost failed:", e));
}
