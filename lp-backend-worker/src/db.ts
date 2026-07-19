// Neon Postgres data layer (HTTP driver — stateless, ideal for the edge).
//
// Column naming in the live DB is inconsistent (created by the old Python bot):
//   company_knowledge/leads/decisions/founder_alerts/report_ledger use camelCase
//   ("createdAt"/"updatedAt") which MUST be double-quoted in SQL, while
//   tickets/comments/attachments use snake_case (created_at). We respect that
//   exactly here so we reuse the founder's existing data instead of forking it.
import { neon } from "@neondatabase/serverless";
import { Env } from "./types";

type Sql = (strings: TemplateStringsArray, ...values: any[]) => Promise<any[]> & {
  query: (text: string, params?: any[]) => Promise<any[]>;
};

let _sql: any = null;
function sql(env: Env): any {
  if (!_sql) _sql = neon(env.DATABASE_URL);
  return _sql;
}

/** Parameterised query helper — returns rows as an array. */
export async function q(env: Env, text: string, params: any[] = []): Promise<any[]> {
  const s = sql(env);
  return (await s.query(text, params)) as any[];
}

let _schemaReady = false;
/** Idempotently create the tables the Worker owns but the old bot never made. */
export async function ensureSchema(env: Env): Promise<void> {
  if (_schemaReady) return;
  await q(
    env,
    `CREATE TABLE IF NOT EXISTS conversation_state (
       user_id TEXT PRIMARY KEY,
       memory JSONB NOT NULL DEFAULT '[]'::jsonb,
       last_updated TIMESTAMP DEFAULT NOW()
     )`
  );
  await q(
    env,
    `CREATE TABLE IF NOT EXISTS expenses (
       id SERIAL PRIMARY KEY,
       amount NUMERIC NOT NULL,
       category VARCHAR(120),
       vertical VARCHAR(120),
       note TEXT,
       created_at TIMESTAMP DEFAULT NOW()
     )`
  );
  await q(
    env,
    `CREATE TABLE IF NOT EXISTS tickets (
       id TEXT PRIMARY KEY,
       title TEXT NOT NULL,
       description TEXT,
       assignee_name TEXT,
       status TEXT DEFAULT 'New',
       priority TEXT DEFAULT 'Medium',
       story_points INTEGER DEFAULT 1,
       start_date DATE,
       end_date DATE,
       labels TEXT,
       thread_id TEXT,
       created_at TIMESTAMP DEFAULT NOW(),
       updated_at TIMESTAMP DEFAULT NOW()
     )`
  ).catch(() => {});
  // Backfill columns so each ticket can render like an Azure DevOps card.
  await q(env, `ALTER TABLE tickets ADD COLUMN IF NOT EXISTS thread_id TEXT`).catch(() => {});
  await q(env, `ALTER TABLE tickets ADD COLUMN IF NOT EXISTS story_points INTEGER DEFAULT 1`).catch(() => {});
  await q(env, `ALTER TABLE tickets ADD COLUMN IF NOT EXISTS start_date DATE`).catch(() => {});
  await q(env, `ALTER TABLE tickets ADD COLUMN IF NOT EXISTS end_date DATE`).catch(() => {});
  await q(env, `ALTER TABLE tickets ADD COLUMN IF NOT EXISTS labels TEXT`).catch(() => {});
  await q(env, `ALTER TABLE tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()`).catch(() => {});
  _schemaReady = true;
}

// --- Business knowledge (the "Business Brain" memory) ----------------------

export async function getCompanyKnowledge(env: Env): Promise<string> {
  const rows = await q(env, `SELECT topic, content FROM company_knowledge ORDER BY "updatedAt" DESC`);
  if (!rows.length) return "(No company knowledge recorded yet.)";
  return rows.map((r) => `## ${r.topic}\n${r.content}`).join("\n\n");
}

export async function upsertCompanyKnowledge(env: Env, topic: string, content: string): Promise<boolean> {
  const existing = await q(env, `SELECT id FROM company_knowledge WHERE lower(topic) = lower($1) LIMIT 1`, [topic]);
  if (existing.length) {
    await q(env, `UPDATE company_knowledge SET content = $1, "updatedAt" = NOW() WHERE id = $2`, [content, existing[0].id]);
  } else {
    await q(env, `INSERT INTO company_knowledge (topic, content, "updatedAt") VALUES ($1, $2, NOW())`, [topic, content]);
  }
  return true;
}

// --- Leads -----------------------------------------------------------------

export async function listLeads(env: Env, status?: string): Promise<any[]> {
  if (status) {
    return q(env, `SELECT * FROM leads WHERE lower(status) = lower($1) ORDER BY score DESC NULLS LAST, "createdAt" DESC LIMIT 50`, [status]);
  }
  return q(env, `SELECT * FROM leads ORDER BY score DESC NULLS LAST, "createdAt" DESC LIMIT 50`);
}

export async function saveLead(
  env: Env,
  name: string,
  contact = "",
  source = "",
  summary = "",
  score = 0
): Promise<any> {
  const rows = await q(
    env,
    `INSERT INTO leads (name, contact, source, summary, status, score, "createdAt", "updatedAt")
     VALUES ($1,$2,$3,$4,'new',$5,NOW(),NOW()) RETURNING *`,
    [name, contact, source, summary, score]
  );
  return rows[0];
}

export async function updateLeadStatus(env: Env, id: number, status: string): Promise<any> {
  const rows = await q(env, `UPDATE leads SET status = $1, "updatedAt" = NOW() WHERE id = $2 RETURNING *`, [status, id]);
  return rows[0] || null;
}

// --- Tickets (the board) ---------------------------------------------------
// SUPERSEDED for board data: Admin's Postgres (Epic->Feature->UserStory->Task)
// is now the source of truth for kanban/task data. Board reads/writes go
// through src/adminApi.ts instead. These functions are left in place (and this
// flat `tickets` table keeps existing) but nothing in src/ calls them anymore
// as of the Admin-API migration — do not wire new call sites to them.

export async function listTickets(env: Env, status?: string): Promise<any[]> {
  await ensureSchema(env);
  if (status) {
    return q(
      env,
      `SELECT id, title, description, status, priority, assignee_name, start_date, end_date, story_points, labels, thread_id, created_at, updated_at
         FROM tickets
        WHERE lower(status) = lower($1)
        ORDER BY created_at DESC LIMIT 120`,
      [status]
    );
  }
  return q(
    env,
    `SELECT id, title, description, status, priority, assignee_name, start_date, end_date, story_points, labels, thread_id, created_at, updated_at
       FROM tickets
      WHERE lower(COALESCE(status,'')) NOT IN ('closed','resolved','completed')
      ORDER BY created_at DESC LIMIT 120`
  );
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
): Promise<any> {
  await ensureSchema(env); // guarantees the thread_id link column exists
  const id = "LP-" + Date.now().toString(36).toUpperCase();
  const points = Math.max(0, Math.round(Number(story_points || 1))) || 1;
  const due = /^\d{4}-\d{2}-\d{2}$/.test(String(end_date || "")) ? String(end_date) : null;
  const rows = await q(
    env,
    `INSERT INTO tickets (id, title, description, assignee_name, status, priority, story_points, end_date, labels, created_at, updated_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),NOW())
     RETURNING id, title, description, status, priority, assignee_name, start_date, story_points, end_date, labels, thread_id, created_at, updated_at`,
    [id, title, description, assignee_name, status, priority, points, due, labels || null]
  );
  return rows[0];
}

export async function updateTicketStatus(env: Env, id: string, status: string): Promise<any> {
  await ensureSchema(env);
  const rows = await q(
    env,
    `UPDATE tickets SET status = $1, updated_at = NOW() WHERE id = $2
     RETURNING id, title, description, status, priority, assignee_name, start_date, story_points, end_date, labels, thread_id, created_at, updated_at`,
    [status, id]
  );
  return rows[0] || null;
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

/** Update editable work-item fields and return the hydrated card. */
export async function updateTicket(env: Env, id: string, patch: TicketPatch): Promise<any> {
  await ensureSchema(env);
  const current = await getTicket(env, id);
  if (!current) return null;
  const title = cleanText(patch.title ?? current.title, 180) || current.title;
  const description = cleanLongText(patch.description ?? current.description ?? "", 2800);
  const status = cleanText(patch.status ?? current.status ?? "New", 40) || "New";
  const priority = normalizePriority(patch.priority ?? current.priority ?? "Medium");
  const assignee = cleanText(patch.assignee_name ?? current.assignee_name ?? "", 80);
  const points = normalizePoints(patch.story_points ?? current.story_points ?? 1);
  const due = normalizeDate(patch.end_date === undefined ? current.end_date : patch.end_date);
  const labels = cleanText(patch.labels ?? current.labels ?? "", 240) || null;
  const rows = await q(
    env,
    `UPDATE tickets
        SET title = $1,
            description = $2,
            status = $3,
            priority = $4,
            assignee_name = $5,
            story_points = $6,
            end_date = $7,
            labels = $8,
            updated_at = NOW()
      WHERE id = $9
      RETURNING id, title, description, status, priority, assignee_name, start_date, story_points, end_date, labels, thread_id, created_at, updated_at`,
    [title, description, status, priority, assignee, points, due, labels, id]
  );
  return rows[0] || null;
}

/** Fetch a single ticket by id (with everything needed to render its card). */
export async function getTicket(env: Env, id: string): Promise<any> {
  await ensureSchema(env);
  const rows = await q(
    env,
    `SELECT id, title, description, status, priority, assignee_name, start_date, story_points, end_date, labels, thread_id, created_at, updated_at FROM tickets WHERE id = $1 LIMIT 1`,
    [id]
  );
  return rows[0] || null;
}

/** Persist the Discord forum thread id for a ticket (the DB<->board link). */
export async function setTicketThread(env: Env, id: string, threadId: string): Promise<void> {
  await ensureSchema(env);
  await q(env, `UPDATE tickets SET thread_id = $1, updated_at = NOW() WHERE id = $2`, [threadId, id]);
}

/** Tickets that exist in the DB but have no forum post yet (for /board_sync). */
export async function ticketsMissingThread(env: Env): Promise<any[]> {
  await ensureSchema(env);
  return q(
    env,
    `SELECT id, title, description, status, priority, assignee_name, start_date, story_points, end_date, labels, thread_id, created_at, updated_at
       FROM tickets
      WHERE thread_id IS NULL AND lower(COALESCE(status,'')) NOT IN ('closed','resolved','completed')
      ORDER BY created_at ASC LIMIT 50`
  );
}

function cleanText(value: any, max: number): string {
  return String(value ?? "").replace(/\s+/g, " ").trim().slice(0, max);
}

function cleanLongText(value: any, max: number): string {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+/g, " ")
    .trim()
    .slice(0, max);
}

function normalizePriority(value: any): string {
  const raw = cleanText(value, 20).toLowerCase();
  if (raw === "critical") return "Critical";
  if (raw === "high") return "High";
  if (raw === "low") return "Low";
  return "Medium";
}

function normalizePoints(value: any): number {
  const n = Math.round(Number(value ?? 1));
  if (!Number.isFinite(n)) return 1;
  return Math.max(0, Math.min(99, n));
}

function normalizeDate(value: any): string | null {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const ymd = raw.includes("T") ? raw.slice(0, 10) : raw;
  return /^\d{4}-\d{2}-\d{2}$/.test(ymd) ? ymd : null;
}

// --- Expenses --------------------------------------------------------------

export async function logExpense(env: Env, amount: number, category = "", vertical = "", note = ""): Promise<any> {
  await ensureSchema(env);
  const rows = await q(
    env,
    `INSERT INTO expenses (amount, category, vertical, note, created_at) VALUES ($1,$2,$3,$4,NOW()) RETURNING *`,
    [amount, category, vertical, note]
  );
  return rows[0];
}

export async function expenseSummary(env: Env, days = 30): Promise<{ total: number; byCategory: any[] }> {
  await ensureSchema(env);
  const total = await q(env, `SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE created_at >= NOW() - ($1 || ' days')::interval`, [String(days)]);
  const byCat = await q(env, `SELECT category, COALESCE(SUM(amount),0) AS total FROM expenses WHERE created_at >= NOW() - ($1 || ' days')::interval GROUP BY category ORDER BY total DESC`, [String(days)]);
  return { total: Number(total[0]?.total || 0), byCategory: byCat };
}

// --- Council decision log --------------------------------------------------

export async function recordDecision(env: Env, question: string, lead: string, second: string, verdict: string): Promise<void> {
  await q(
    env,
    `INSERT INTO decisions (question, lead_answer, second_answer, verdict, "createdAt") VALUES ($1,$2,$3,$4,NOW())`,
    [question, lead, second, verdict]
  );
}

export async function listDecisions(env: Env, limit = 10): Promise<any[]> {
  return q(env, `SELECT id, question, verdict, "createdAt" FROM decisions ORDER BY "createdAt" DESC LIMIT $1`, [limit]);
}

// --- Founder escalations ---------------------------------------------------

export async function recordAlert(env: Env, severity: string, topic: string, summary: string): Promise<any> {
  const existing = await q(
    env,
    `SELECT *
       FROM founder_alerts
      WHERE lower(topic) = lower($1)
        AND lower(severity) = lower($2)
        AND "createdAt" >= NOW() - interval '24 hours'
      ORDER BY "createdAt" DESC
      LIMIT 1`,
    [topic, severity]
  ).catch(() => []);
  if (existing.length) return { ...existing[0], duplicate: true };

  const rows = await q(
    env,
    `INSERT INTO founder_alerts (severity, topic, summary, delivered, "createdAt") VALUES ($1,$2,$3,false,NOW()) RETURNING *`,
    [severity, topic, summary]
  );
  return rows[0];
}

export async function undeliveredAlerts(env: Env): Promise<any[]> {
  return q(env, `SELECT * FROM founder_alerts WHERE delivered = false ORDER BY "createdAt" ASC LIMIT 20`);
}

export async function markAlertDelivered(env: Env, id: number): Promise<void> {
  await q(env, `UPDATE founder_alerts SET delivered = true WHERE id = $1`, [id]);
}

// --- Report ledger (autonomous-loop de-dup) --------------------------------

export async function recentReportSignatures(env: Env, focus: string, hours = 12): Promise<Set<string>> {
  const rows = await q(
    env,
    `SELECT signature FROM report_ledger WHERE focus = $1 AND "createdAt" >= NOW() - ($2 || ' hours')::interval`,
    [focus, String(hours)]
  );
  return new Set(rows.map((r) => r.signature));
}

export async function recordReport(env: Env, focus: string, signature: string, summary: string): Promise<void> {
  await q(env, `INSERT INTO report_ledger (focus, signature, summary, "createdAt") VALUES ($1,$2,$3,NOW())`, [focus, signature, summary.slice(0, 4000)]);
}

// --- Conversation memory ---------------------------------------------------

export async function getMemory(env: Env, userId: string): Promise<{ role: "user" | "assistant"; content: string }[]> {
  await ensureSchema(env);
  const rows = await q(env, `SELECT memory FROM conversation_state WHERE user_id = $1 LIMIT 1`, [userId]);
  if (!rows.length) return [];
  const mem = rows[0].memory;
  return Array.isArray(mem) ? mem : [];
}

export async function saveMemory(env: Env, userId: string, turns: { role: "user" | "assistant"; content: string }[]): Promise<void> {
  await ensureSchema(env);
  const recent = turns.slice(-20);
  await q(
    env,
    `INSERT INTO conversation_state (user_id, memory, last_updated) VALUES ($1, $2::jsonb, NOW())
     ON CONFLICT (user_id) DO UPDATE SET memory = $2::jsonb, last_updated = NOW()`,
    [userId, JSON.stringify(recent)]
  );
}

// --- Whole-business snapshot ----------------------------------------------

export async function companySnapshot(env: Env): Promise<string> {
  await ensureSchema(env);
  const [tickets, leads, decisions, alerts, spend] = await Promise.all([
    q(env, `SELECT status, COUNT(*) AS n FROM tickets GROUP BY status`),
    q(env, `SELECT status, COUNT(*) AS n FROM leads GROUP BY status`),
    q(env, `SELECT COUNT(*) AS n FROM decisions`),
    q(env, `SELECT COUNT(*) AS n FROM founder_alerts WHERE delivered = false`),
    q(env, `SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE created_at >= NOW() - INTERVAL '7 days'`).catch(() => [{ total: 0 }]),
  ]);
  const fmt = (rows: any[]) => (rows.length ? rows.map((r) => `${r.status || "?"}: ${r.n}`).join(", ") : "none");
  return [
    `Board (tickets by status): ${fmt(tickets)}`,
    `Leads by status: ${fmt(leads)}`,
    `Council decisions logged: ${decisions[0]?.n ?? 0}`,
    `Pending founder escalations: ${alerts[0]?.n ?? 0}`,
    `Spend (7d): $${Number(spend[0]?.total || 0).toFixed(2)}`,
  ].join("\n");
}
