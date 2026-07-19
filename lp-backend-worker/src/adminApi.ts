// Admin dashboard HTTP client — the new source of truth for kanban/task data.
//
// LP_Bot no longer owns the `tickets` table (see db.ts's now-superseded ticket
// functions). Admin's Postgres (Epic->Feature->UserStory->Task) is canonical;
// this module talks to Admin's bot-facing REST API and translates its `Task`
// shape at the boundary so every existing call site (board.ts's TicketCard,
// commands.ts, tools.ts, index.ts) keeps working unchanged. Field translations
// that live here on purpose, not in board.ts:
//   - Admin's numeric `id`      -> stringified TicketCard.id (e.g. "42")
//   - Admin's `board_status`    <-> TicketCard.status
//   - Admin's `due_date`        <-> TicketCard.end_date
//   - Admin's `labels` (array)  <-> TicketCard.labels (comma-joined string)
//   - Admin's `discord_thread_id` <-> TicketCard.thread_id
import { Env } from "./types";

/** Shape every call site already expects (board.ts's TicketCard, plus the
 *  extra bookkeeping fields index.ts/commands.ts read off tickets). */
export interface TicketCard {
  id: string;
  title: string;
  description: string;
  assignee_name: string;
  priority: string;
  status: string;
  story_points: number;
  end_date: string | null;
  labels: string; // comma-joined, matches the old tickets.labels column
  thread_id: string | null;
  start_date: string | null; // Admin does not track this separately; always null.
  created_at?: string;
  updated_at?: string;
}

export interface TicketPatch {
  title?: string;
  description?: string;
  status?: string;
  priority?: string;
  assignee_name?: string;
  story_points?: number | string | null;
  end_date?: string | null;
  labels?: string | null;
}

class AdminApiError extends Error {}

function baseUrl(env: Env): string {
  const raw = env.ADMIN_API_BASE_URL || "";
  return raw.replace(/\/+$/, "");
}

async function adminFetch(env: Env, path: string, init?: RequestInit): Promise<any> {
  const base = baseUrl(env);
  if (!base) throw new AdminApiError("ADMIN_API_BASE_URL is not configured");
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": env.ADMIN_API_KEY || "",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new AdminApiError(`Admin API ${init?.method || "GET"} ${path} -> ${res.status}: ${text.slice(0, 300)}`);
  }
  if (res.status === 204) return {};
  return res.json().catch(() => ({}));
}

function labelsToArray(labels?: string | null): string[] {
  return String(labels ?? "")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function labelsToString(labels: any): string {
  if (Array.isArray(labels)) return labels.filter(Boolean).join(",");
  return String(labels ?? "");
}

/** Translate an Admin `Task` into the TicketCard shape every call site expects. */
function toCard(task: any): TicketCard {
  return {
    id: String(task?.id ?? ""),
    title: String(task?.title ?? ""),
    description: String(task?.description ?? ""),
    assignee_name: String(task?.assignee_name ?? ""),
    priority: String(task?.priority ?? "Medium"),
    status: String(task?.board_status ?? "New"),
    story_points: Number(task?.story_points ?? 1),
    end_date: task?.due_date ?? null,
    labels: labelsToString(task?.labels),
    thread_id: task?.discord_thread_id ? String(task.discord_thread_id) : null,
    start_date: null,
    created_at: task?.created_at,
    updated_at: task?.updated_at,
  };
}

/** List tasks, optionally filtered by board column. */
export async function listTickets(env: Env, status?: string): Promise<TicketCard[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const data = await adminFetch(env, `/api/bot/tasks${qs}`);
  const tasks = Array.isArray(data?.tasks) ? data.tasks : [];
  return tasks.map(toCard);
}

/** Fetch a single ticket by id. Admin's bot API has no single-task GET route
 *  (see contract), so this lists everything and filters client-side — flagged
 *  as a follow-up: ask Admin for GET /api/bot/tasks/:id if this list grows large. */
export async function getTicket(env: Env, id: string): Promise<TicketCard | null> {
  const numericId = Number(String(id).trim());
  if (!Number.isFinite(numericId)) return null;
  const all = await listTickets(env);
  return all.find((t) => Number(t.id) === numericId) || null;
}

export async function createTicket(
  env: Env,
  title: string,
  description = "",
  assignee_name = "",
  priority = "Medium",
  status = "New",
  story_points: number | string = 1,
  end_date = "",
  labels = ""
): Promise<TicketCard> {
  const body: Record<string, any> = {
    title,
    description,
    assignee_name,
    priority,
    board_status: status,
    story_points: Math.max(0, Math.round(Number(story_points || 1))) || 1,
    tags: labelsToArray(labels),
  };
  if (end_date) body.due_date = end_date;
  const data = await adminFetch(env, `/api/bot/tasks`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return toCard(data?.task);
}

/** Update editable work-item fields and return the hydrated card, or null if
 *  the ticket does not exist. */
export async function updateTicket(env: Env, id: string, patch: TicketPatch): Promise<TicketCard | null> {
  const numericId = Number(String(id).trim());
  if (!Number.isFinite(numericId)) return null;

  const body: Record<string, any> = {};
  if (patch.title !== undefined) body.title = patch.title;
  if (patch.description !== undefined) body.description = patch.description;
  if (patch.status !== undefined) body.board_status = patch.status;
  if (patch.priority !== undefined) body.priority = patch.priority;
  if (patch.assignee_name !== undefined) body.assignee_name = patch.assignee_name;
  if (patch.story_points !== undefined) body.story_points = Math.max(0, Math.round(Number(patch.story_points || 1))) || 1;
  if (patch.end_date !== undefined) body.due_date = patch.end_date;
  if (patch.labels !== undefined) body.tags = labelsToArray(patch.labels);

  try {
    const data = await adminFetch(env, `/api/bot/tasks/${numericId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    return toCard(data?.task);
  } catch (e: any) {
    if (e instanceof AdminApiError && /-> 404/.test(e.message)) return null;
    throw e;
  }
}

/** Convenience wrapper matching the old db.updateTicketStatus(env, id, status) shape. */
export async function updateTicketStatus(env: Env, id: string, status: string): Promise<TicketCard | null> {
  return updateTicket(env, id, { status });
}

/** Persist the Discord forum thread id for a ticket (the DB<->board link). */
export async function setTicketThread(env: Env, id: string, threadId: string): Promise<void> {
  const numericId = Number(String(id).trim());
  if (!Number.isFinite(numericId)) return;
  await adminFetch(env, `/api/bot/tasks/${numericId}`, {
    method: "PATCH",
    body: JSON.stringify({ discord_thread_id: threadId }),
  });
}

/** Tickets that exist in Admin but have no forum post yet (for /board_sync).
 *  No dedicated Admin endpoint for this — fetch active tickets and filter
 *  client-side for a missing discord_thread_id. */
export async function ticketsMissingThread(env: Env): Promise<TicketCard[]> {
  const all = await listTickets(env);
  return all.filter((t) => t.status !== "Closed" && !t.thread_id).slice(0, 50);
}
