import { Env } from "./types";
import { editChannelMessage, postPayloadToChannel, type DiscordMessagePayload } from "./discord";
import * as board from "./board";
import * as adminApi from "./adminApi";

const DASHBOARD_CHANNEL_KEY = "kanban:dashboard:channel";
const DASHBOARD_HEADER_KEY = "kanban:dashboard:header";
const DASHBOARD_LANE_PREFIX = "kanban:dashboard:lane:";

async function getDashboardChannel(env: Env, fallback?: string): Promise<string> {
  if (fallback) return fallback;
  if (env.KANBAN_DASHBOARD_CHANNEL_ID) return env.KANBAN_DASHBOARD_CHANNEL_ID;
  return (await env.LP_STATE.get(DASHBOARD_CHANNEL_KEY).catch(() => null)) || "";
}

function groupRows(rows: any[]): Map<board.Column, any[]> {
  const byCol = new Map<board.Column, any[]>();
  for (const c of board.ACTIVE_COLUMNS) byCol.set(c, []);
  for (const t of rows) {
    const col = board.normalizeColumn(t.status);
    if (col !== "Closed") byCol.get(col as Exclude<board.Column, "Closed">)!.push(t);
  }
  return byCol;
}

export async function publishBoardDashboard(env: Env, requestedChannelId?: string): Promise<string> {
  const channelId = await getDashboardChannel(env, requestedChannelId);
  if (!channelId) {
    return "⚠️ Run `/board_publish` inside the text channel that should hold the DevOps board, or set `KANBAN_DASHBOARD_CHANNEL_ID`.";
  }
  await env.LP_STATE.put(DASHBOARD_CHANNEL_KEY, channelId).catch(() => {});
  const ok = await refreshPublishedDashboard(env, channelId);
  if (!ok) return `⚠️ I could not publish the board in <#${channelId}>. Check bot permissions: View Channel, Send Messages, Embed Links, Read Message History.`;
  return `✅ Published/refreshed the Azure-style DevOps board in <#${channelId}>. Ticket moves will keep it updated.`;
}

export async function refreshPublishedDashboard(env: Env, requestedChannelId?: string): Promise<boolean> {
  const channelId = await getDashboardChannel(env, requestedChannelId);
  if (!channelId) return false;
  const rows = await adminApi.listTickets(env).catch(() => []);
  return upsertDashboardMessages(env, channelId, rows, groupRows(rows));
}

async function upsertDashboardMessages(env: Env, channelId: string, rows: any[], byCol: Map<board.Column, any[]>): Promise<boolean> {
  const total = rows.length;
  const blocked = byCol.get("Blocked")?.length || 0;
  const activePoints = rows.reduce((sum, t) => sum + (Number(t.story_points || 0) || 0), 0);
  const overLimit = board.ACTIVE_COLUMNS.filter((c) => {
    const limit = board.WIP_LIMITS[c];
    return limit && (byCol.get(c)?.length || 0) > limit;
  });

  const header: DiscordMessagePayload = {
    content: "**LaunchPixel DevOps Board**",
    embeds: [
      {
        title: "Azure-style Sprint Board",
        description: [
          env.KANBAN_FORUM_CHANNEL_ID ? `Detailed cards: <#${env.KANBAN_FORUM_CHANNEL_ID}>` : "Detailed forum cards are not wired yet.",
          `${total} active card${total === 1 ? "" : "s"} · ${activePoints} story point${activePoints === 1 ? "" : "s"} · ${blocked} blocked`,
          overLimit.length ? `WIP over limit: ${overLimit.join(", ")}` : "WIP limits healthy",
        ].join("\n"),
        color: blocked ? board.COLUMN_COLOR.Blocked : board.COLUMN_COLOR.Planned,
        fields: board.ACTIVE_COLUMNS.map((c) => ({ name: `${board.COLUMN_EMOJI[c]} ${c}`, value: board.wipLabel(c, byCol.get(c)?.length || 0), inline: true })),
        footer: { text: "Managed by LP_Bot. Use /ticket_new, /ticket_move, or card dropdowns." },
        timestamp: new Date().toISOString(),
      },
    ],
    allowed_mentions: { parse: [] },
  };

  const headerOk = await upsertStoredMessage(env, channelId, DASHBOARD_HEADER_KEY, header);
  const laneResults = await Promise.all(
    board.ACTIVE_COLUMNS.map((col) =>
      upsertStoredMessage(env, channelId, `${DASHBOARD_LANE_PREFIX}${col}`, lanePayload(col, byCol.get(col) || []))
    )
  );
  return Boolean(headerOk && laneResults.every(Boolean));
}

async function upsertStoredMessage(env: Env, channelId: string, key: string, payload: DiscordMessagePayload): Promise<boolean> {
  const existing = await env.LP_STATE.get(key).catch(() => null);
  if (existing) {
    const edited = await editChannelMessage(env, channelId, existing, payload).catch(() => null);
    if (edited?.id) return true;
  }
  const posted = await postPayloadToChannel(env, channelId, payload).catch(() => null);
  if (!posted?.id) return false;
  await env.LP_STATE.put(key, String(posted.id)).catch(() => {});
  return true;
}

function lanePayload(col: Exclude<board.Column, "Closed">, items: any[]): DiscordMessagePayload {
  const limit = board.WIP_LIMITS[col];
  const state = limit && items.length > limit ? "Over WIP limit" : items.length ? "In motion" : "Empty";
  return {
    content: `${board.COLUMN_EMOJI[col]} **${col}**`,
    embeds: [
      {
        title: board.columnHeading(col, items.length),
        description: renderLaneCards(items, col),
        color: board.COLUMN_COLOR[col],
        footer: { text: `${state}${limit ? ` · limit ${limit}` : ""}` },
      },
    ],
    allowed_mentions: { parse: [] },
  };
}

function renderLaneCards(items: any[], col: board.Column): string {
  if (!items.length) return col === "Blocked" ? "_No blockers right now._" : "_No cards in this lane._";
  const lines: string[] = [];
  for (const t of items) {
    const next = boardCardBlock(t);
    if ([...lines, next].join("\n\n").length > 3800) break;
    lines.push(next);
  }
  if (lines.length < items.length) lines.push(`…and ${items.length - lines.length} more cards`);
  return lines.join("\n\n");
}

function boardCardBlock(t: any): string {
  const id = String(t.id || "?");
  const title = String(t.title || "Untitled").slice(0, 80);
  const owner = t.assignee_name ? String(t.assignee_name).slice(0, 32) : "Unassigned";
  const points = t.story_points === 0 || t.story_points ? `${t.story_points} SP` : "1 SP";
  const labels = board.labelList(t.labels);
  const labelText = labels.length ? `\n${labels.map((l) => `\`${l.slice(0, 18)}\``).join(" ")}` : "";
  const link = t.thread_id ? `\nCard: <#${t.thread_id}>` : "";
  return `**${id} · ${title}**\n${priorityGlyph(String(t.priority || "Medium"))} · ${points} · ${owner}${formatDue(t.end_date)}${labelText}${link}`;
}

function priorityGlyph(priority: string): string {
  switch (priority.toLowerCase()) {
    case "critical":
      return "🔴 Critical";
    case "high":
      return "🟠 High";
    case "low":
      return "🟢 Low";
    default:
      return "🟡 Medium";
  }
}

function formatDue(value?: string | Date | null): string {
  if (!value) return "";
  if (value instanceof Date) return ` · due ${value.toISOString().slice(0, 10)}`;
  const s = String(value);
  return s ? ` · due ${s.includes("T") ? s.slice(0, 10) : s.slice(0, 20)}` : "";
}
