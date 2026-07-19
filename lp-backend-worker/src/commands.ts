// Slash-command dispatch: map each command to an agent instruction (or a direct
// DB action) and return the reply text. Run inside ctx.waitUntil() after the
// interaction has already been deferred, so long LLM calls never time out.
import { Env } from "./types";
import { SYSTEM_PROMPT } from "./prompts";
import { runAgent } from "./agent";
import { consultCouncil } from "./council";
import type { DiscordReply } from "./discord";
import { publishBoardDashboard, refreshPublishedDashboard } from "./dashboard";
import * as db from "./db";
import * as adminApi from "./adminApi";
import * as board from "./board";

type Opts = Record<string, any>;

export async function handleCommand(env: Env, name: string, opts: Opts, userId: string, userName: string, channelId?: string): Promise<DiscordReply> {
  switch (name) {
    case "ask": {
      const history = await db.getMemory(env, userId).catch(() => []);
      const query = String(opts.query || "Hello");
      const reply = await runAgent(env, SYSTEM_PROMPT, `${userName} asks: ${query}`, history);
      await db
        .saveMemory(env, userId, [...history, { role: "user", content: query }, { role: "assistant", content: reply }])
        .catch(() => {});
      return reply;
    }

    case "board":
      return renderBoard(env);

    case "devops":
      return {
        content: `LaunchPixel DevOps Board: ${boardUrl(env, true)}\nUse it for Azure-style drag/drop planning; Discord forum cards stay synced behind it.`,
        allowed_mentions: { parse: [] },
      };

    case "board_publish":
      return publishBoardDashboard(env, channelId);

    case "standup":
      return runAgent(env, SYSTEM_PROMPT, "Produce today's standup summary from recent board activity via list_tickets. Group by status, name owners, and call out blockers.");

    case "leads":
      return runAgent(env, SYSTEM_PROMPT, "Summarise the lead pipeline. Call list_leads, then report how many leads at each stage, the top open leads by score, and which need follow-up right now.");

    case "finance":
      return runAgent(env, SYSTEM_PROMPT, "Summarise recent finances. Call get_expense_summary (30 days), then report total spend, the breakdown by category, and flag anything unusual worth the founder's attention.");

    case "business":
      return runAgent(env, SYSTEM_PROMPT, `Answer this question about LaunchPixel's business by consulting ask_business_brain first, then company_snapshot for live numbers if relevant.\n\nQuestion: ${String(opts.query || "")}`);

    case "briefing":
      return runAgent(env, SYSTEM_PROMPT, "Produce a founder-ready morning briefing. Call company_snapshot and list_decisions, then deliver: board health (active/overdue), the lead pipeline (top open leads + follow-ups), 7-day spend, pending escalations, and the single most important thing to act on today. Lead with the headline, then bullets.");

    case "status":
      return runAgent(env, SYSTEM_PROMPT, "Give a short status-of-the-business read by calling company_snapshot. Report tickets active vs done, the lead pipeline at a glance, 7-day spend, and any pending founder escalations. Keep it to a few lines.");

    case "decisions": {
      const rows = await db.listDecisions(env, 10);
      if (!rows.length) return "No council decisions logged yet.";
      return "🧠 **Recent Council Decisions**\n" + rows.map((r) => `**#${r.id}** — ${String(r.question).slice(0, 80)}\n${String(r.verdict || "").slice(0, 220)}`).join("\n\n");
    }

    case "council":
      return consultCouncil(env, String(opts.decision || ""));

    case "learn": {
      await db.upsertCompanyKnowledge(env, String(opts.topic), String(opts.content));
      return `✅ Learned it. Saved under **${opts.topic}** — I'll use this going forward.`;
    }

    case "ticket_new": {
      const col = board.normalizeColumn(String(opts.status || "New"));
      const priority = String(opts.priority || "Medium");
      const storyPoints = Number(opts.story_points || 1);
      const dueDate = String(opts.due_date || "");
      const labels = String(opts.labels || "");
      const t = await adminApi.createTicket(env, String(opts.title), String(opts.description || ""), String(opts.assignee || ""), priority, col, storyPoints, dueDate, labels);
      // Post the card onto the forum board and remember the thread.
      const post = await board.createForumPost(env, t).catch(() => null);
      if (post?.thread_id) await adminApi.setTicketThread(env, t.id, post.thread_id).catch(() => {});
      await refreshPublishedDashboard(env).catch(() => {});
      const link = post?.thread_id ? ` → <#${post.thread_id}>` : boardHint(env);
      const due = dueDate ? ` · due \`${dueDate}\`` : "";
      return `✅ Created **${t.id}** — ${t.title} in **${col}** (${t.story_points || storyPoints || 1} SP${due})${link}`;
    }

    case "ticket_move": {
      const col = board.normalizeColumn(String(opts.status || ""));
      const t = await adminApi.updateTicketStatus(env, String(opts.id), col);
      if (!t) return `⚠️ No ticket with id \`${opts.id}\`.`;
      // Move the card on the board — creating the post first if it never had one.
      let threadId: string | undefined = t.thread_id || undefined;
      if (!threadId) {
        const post = await board.createForumPost(env, t).catch(() => null);
        if (post?.thread_id) {
          threadId = post.thread_id;
          await adminApi.setTicketThread(env, t.id, threadId).catch(() => {});
        }
      } else {
        await board.moveForumPost(env, threadId, t, col, userName).catch(() => {});
      }
      await refreshPublishedDashboard(env).catch(() => {});
      const link = threadId ? ` → <#${threadId}>` : "";
      return `✅ **${t.id}** moved to **${col}**${link}`;
    }

    case "ticket_view":
      return renderTicketView(env, String(opts.id || ""));

    case "board_sync":
      return syncBoard(env);

    default:
      return `Command \`/${name}\` isn't wired up yet.`;
  }
}

export async function handleComponent(env: Env, body: any, _userId: string, userName: string): Promise<DiscordReply> {
  const parsed = board.parseMoveComponent(body?.data?.custom_id, body?.data?.values || []);
  if (!parsed) return "⚠️ That board control is not wired up.";

  const t = await adminApi.updateTicketStatus(env, parsed.ticketId, parsed.column);
  if (!t) return `⚠️ No ticket with id \`${parsed.ticketId}\`.`;

  let threadId: string | undefined = t.thread_id || body?.channel_id || undefined;
  if (threadId && !t.thread_id) await adminApi.setTicketThread(env, t.id, threadId).catch(() => {});

  if (!threadId) {
    const post = await board.createForumPost(env, t).catch(() => null);
    if (post?.thread_id) {
      threadId = post.thread_id;
      await adminApi.setTicketThread(env, t.id, threadId).catch(() => {});
    }
  } else {
    await board.moveForumPost(env, threadId, t, parsed.column, userName).catch(() => {});
  }

  await refreshPublishedDashboard(env).catch(() => {});
  const link = threadId ? ` → <#${threadId}>` : "";
  return { content: `✅ **${t.id}** moved to **${parsed.column}**${link}`, allowed_mentions: { parse: [] } };
}

// --- Board rendering / sync helpers ---------------------------------------

/** A pointer to the forum channel if it's configured, else empty. */
function boardHint(env: Env): string {
  return env.KANBAN_FORUM_CHANNEL_ID ? ` (open <#${env.KANBAN_FORUM_CHANNEL_ID}>)` : "";
}

function boardUrl(env: Env, includeWriteToken = false): string {
  const raw = env.PUBLIC_BOARD_URL || "https://lp-bot.vksh1cool.workers.dev/devops-board";
  if (!includeWriteToken || !env.BOARD_ADMIN_TOKEN) return raw;
  const url = new URL(raw);
  url.searchParams.set("token", env.BOARD_ADMIN_TOKEN);
  return url.toString();
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

/** Live Azure DevOps-style snapshot grouped by columns. */
async function renderBoard(env: Env): Promise<DiscordReply> {
  const rows = await adminApi.listTickets(env).catch(() => []);
  const byCol = groupRows(rows);

  const total = rows.length;
  const blocked = byCol.get("Blocked") || [];
  const overLimit = board.ACTIVE_COLUMNS.filter((c) => {
    const limit = board.WIP_LIMITS[c];
    return limit && (byCol.get(c)?.length || 0) > limit;
  });
  const forum = env.KANBAN_FORUM_CHANNEL_ID ? `Full card view: <#${env.KANBAN_FORUM_CHANNEL_ID}>` : "Set KANBAN_FORUM_CHANNEL_ID to enable forum cards.";
  const fields = board.ACTIVE_COLUMNS.map((col) => {
    const items = byCol.get(col) || [];
    return {
      name: board.columnHeading(col, items.length),
      value: renderColumnItems(items),
      inline: true,
    };
  });

  const embeds: any[] = [
    {
      title: "LaunchPixel Board",
      description: `${forum}\n${total} active card${total === 1 ? "" : "s"}${overLimit.length ? ` · WIP over limit: ${overLimit.join(", ")}` : ""}`,
      color: blocked.length ? 0xe03131 : 0x4c6ef5,
      fields,
      footer: { text: "Use /ticket_new to add a card, /ticket_move or the card dropdown to move it." },
    },
  ];

  if (blocked.length) {
    embeds.push({
      title: "Blocked Cards Need Attention",
      description: blocked.slice(0, 8).map(compactCardLine).join("\n\n").slice(0, 3900),
      color: 0xe03131,
    });
  }

  return { content: `🗂️ **LaunchPixel Azure-style Kanban**\nFull board app: ${boardUrl(env)}\nRun \`/board_publish\` in a text channel to maintain the Discord dashboard there.`, embeds, allowed_mentions: { parse: [] } };
}

function renderColumnItems(items: any[]): string {
  if (!items.length) return "_No cards_";
  const lines: string[] = [];
  for (const t of items) {
    const next = compactCardLine(t);
    if ([...lines, next].join("\n\n").length > 980) break;
    lines.push(next);
  }
  if (lines.length < items.length) lines.push(`…and ${items.length - lines.length} more`);
  return lines.join("\n\n");
}

function compactCardLine(t: any): string {
  const id = String(t.id || "?");
  const title = String(t.title || "Untitled").slice(0, 52);
  const owner = t.assignee_name ? String(t.assignee_name).slice(0, 28) : "Unassigned";
  const points = t.story_points === 0 || t.story_points ? `${t.story_points} SP` : "1 SP";
  const priority = priorityGlyph(String(t.priority || "Medium"));
  const due = formatDue(t.end_date);
  const link = t.thread_id ? ` · <#${t.thread_id}>` : "";
  const labels = board.labelList(t.labels);
  const labelText = labels.length ? `\n${labels.map((l) => `\`${l.slice(0, 18)}\``).join(" ")}` : "";
  return `\`${id}\` **${title}**\n${priority} · ${points} · ${owner}${due}${link}${labelText}`;
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

async function renderTicketView(env: Env, id: string): Promise<DiscordReply> {
  const t = await adminApi.getTicket(env, id.trim());
  if (!t) return `⚠️ No ticket with id \`${id}\`.`;
  const col = board.normalizeColumn(t.status);
  const labels = board.labelList(t.labels);
  const fields: any[] = [
    { name: "State", value: `${board.COLUMN_EMOJI[col]} \`${col}\``, inline: true },
    { name: "Priority", value: priorityGlyph(String(t.priority || "Medium")), inline: true },
    { name: "Owner", value: t.assignee_name || "_Unassigned_", inline: true },
    { name: "Story Points", value: t.story_points ? `${t.story_points} SP` : "1 SP", inline: true },
    { name: "Due", value: formatDue(t.end_date).replace(" · due ", "") || "Not set", inline: true },
  ];
  if (labels.length) fields.push({ name: "Tags", value: labels.map((l) => `\`${l.slice(0, 22)}\``).join(" "), inline: true });
  if (t.thread_id) fields.push({ name: "Execution Thread", value: `<#${t.thread_id}>`, inline: false });
  return {
    embeds: [
      {
        title: `${t.id} · ${String(t.title || "Untitled").slice(0, 180)}`,
        description: String(t.description || "_No description yet._").slice(0, 3500),
        color: board.COLUMN_COLOR[col],
        fields,
        footer: { text: "Use the dropdown below to move this work item." },
      },
    ],
    components: board.renderCardComponents(t),
    allowed_mentions: { parse: [] },
  };
}

/** Backfill forum posts for any DB tickets that don't have one yet. */
async function syncBoard(env: Env): Promise<string> {
  if (!env.KANBAN_FORUM_CHANNEL_ID) return "⚠️ Board not wired yet — set `KANBAN_FORUM_CHANNEL_ID` first.";
  const pending = await adminApi.ticketsMissingThread(env).catch(() => []);
  if (!pending.length) {
    await refreshPublishedDashboard(env).catch(() => {});
    return "✅ Board already in sync — every open ticket has a card. Dashboard refreshed too.";
  }
  let posted = 0;
  for (const t of pending) {
    const post = await board.createForumPost(env, t).catch(() => null);
    if (post?.thread_id) {
      await adminApi.setTicketThread(env, t.id, post.thread_id).catch(() => {});
      posted++;
    }
  }
  await refreshPublishedDashboard(env).catch(() => {});
  return `✅ Synced **${posted}/${pending.length}** ticket(s) onto the board <#${env.KANBAN_FORUM_CHANNEL_ID}> and refreshed the dashboard.`;
}
