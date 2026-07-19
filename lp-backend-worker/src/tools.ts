// Agent tools — JSON-Schema definitions + a single executor. Every tool is
// Neon-backed and wrapped so a failure returns a string to the model instead of
// crashing the run (mirrors the Python bot's safe-tool wrapper).
import { Env, ToolSchema } from "./types";
import { geminiText } from "./llm";
import { consultCouncil } from "./council";
import * as db from "./db";
import * as adminApi from "./adminApi";
import * as board from "./board";
import { refreshPublishedDashboard } from "./dashboard";

const S = (props: Record<string, any>, required: string[] = []) => ({
  type: "object",
  properties: props,
  required,
});

export const TOOL_SCHEMAS: ToolSchema[] = [
  { name: "company_snapshot", description: "Live read of the whole business: tickets by status, leads by status, decisions, pending escalations and 7-day spend. Call before any status/briefing.", parameters: S({}) },
  { name: "list_tickets", description: "List DevOps board tickets. Optional status filter — columns are New, Planned, Refining, Active, Reviewing, Blocked, Closed.", parameters: S({ status: { type: "string" } }) },
  { name: "create_ticket", description: "Create a real work item on the DevOps board. It becomes a Discord forum card and appears on the persistent dashboard. Use only for concrete work, not vague ideas.", parameters: S({ title: { type: "string" }, description: { type: "string" }, assignee_name: { type: "string" }, priority: { type: "string", enum: ["Low", "Medium", "High", "Critical"] }, status: { type: "string", enum: ["New", "Planned", "Refining", "Active", "Reviewing", "Blocked", "Closed"] }, story_points: { type: "number" }, due_date: { type: "string", description: "YYYY-MM-DD" }, labels: { type: "string", description: "Comma-separated tags" } }, ["title"]) },
  { name: "update_ticket_status", description: "Move a ticket to a DevOps board column (New, Planned, Refining, Active, Reviewing, Blocked, Closed). This re-tags its card and refreshes the dashboard.", parameters: S({ id: { type: "string" }, status: { type: "string", enum: ["New", "Planned", "Refining", "Active", "Reviewing", "Blocked", "Closed"] } }, ["id", "status"]) },
  { name: "list_leads", description: "List sales leads in the pipeline, best first. Optional status filter.", parameters: S({ status: { type: "string" } }) },
  { name: "save_lead", description: "Log a real business lead only when there is a concrete company/person/contact/source. Never save placeholder/example leads. score is 0-100 qualification.", parameters: S({ name: { type: "string" }, contact: { type: "string" }, source: { type: "string" }, summary: { type: "string" }, score: { type: "number" } }, ["name"]) },
  { name: "update_lead_status", description: "Update a lead's status by id (e.g. 'new','qualified','won','lost').", parameters: S({ id: { type: "number" }, status: { type: "string" } }, ["id", "status"]) },
  { name: "log_expense", description: "Record a company expense.", parameters: S({ amount: { type: "number" }, category: { type: "string" }, vertical: { type: "string" }, note: { type: "string" } }, ["amount"]) },
  { name: "get_expense_summary", description: "Summarise spend over the last N days (default 30) with a per-category breakdown.", parameters: S({ days: { type: "number" } }) },
  { name: "ask_business_brain", description: "Consult the LaunchPixel Business Brain (company SOPs, KPIs, strategy, positioning). Use for any agency-specific question.", parameters: S({ query: { type: "string" } }, ["query"]) },
  { name: "learn_business_rule", description: "Save or update a business rule/SOP/KPI into company knowledge so the bot gets smarter.", parameters: S({ topic: { type: "string" }, content: { type: "string" } }, ["topic", "content"]) },
  { name: "list_decisions", description: "List recent high-stakes council decisions.", parameters: S({ limit: { type: "number" } }) },
  { name: "escalate_to_founder", description: "Escalate something critical to the founder (Vivek). severity is 'low'|'medium'|'high'|'critical'. Delivered on the next loop tick.", parameters: S({ topic: { type: "string" }, summary: { type: "string" }, severity: { type: "string", enum: ["low", "medium", "high", "critical"] } }, ["topic", "summary", "severity"]) },
  { name: "web_search", description: "Search the public web for a fresh signal (competitor moves, trends, tools). Returns top result snippets.", parameters: S({ query: { type: "string" } }, ["query"]) },
  { name: "consult_council", description: "Convene the Dual-Brain council (Gemini + NVIDIA NIM) for a HIGH-STAKES or irreversible decision — pricing, scoping, pursuing a lead, hiring, sprint priorities. Returns a weighted verdict and logs it to the decision record. Use sparingly; routine lookups do not need the council.", parameters: S({ decision: { type: "string" }, context: { type: "string" } }, ["decision"]) },
];

function j(v: any): string {
  try {
    return typeof v === "string" ? v : JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export async function executeTool(env: Env, name: string, args: Record<string, any>): Promise<string> {
  args = args || {};
  try {
    switch (name) {
      case "company_snapshot":
        return await db.companySnapshot(env);
      case "list_tickets": {
        const rows = await adminApi.listTickets(env, args.status);
        return rows.length ? j(rows) : "No tickets found.";
      }
      case "create_ticket": {
        const col = board.normalizeColumn(args.status || "New");
        const t = await adminApi.createTicket(env, args.title, args.description, args.assignee_name, args.priority, col, args.story_points || 1, args.due_date || "", args.labels || "");
        const post = await board.createForumPost(env, t).catch(() => null);
        if (post?.thread_id) await adminApi.setTicketThread(env, t.id, post.thread_id).catch(() => {});
        await refreshPublishedDashboard(env).catch(() => {});
        return `Created ticket ${t.id}: ${t.title} [${col}]${post ? " (carded on the board)" : ""}`;
      }
      case "update_ticket_status": {
        const col = board.normalizeColumn(String(args.status));
        const t = await adminApi.updateTicketStatus(env, String(args.id), col);
        if (!t) return `No ticket with id ${args.id}.`;
        let threadId: string | undefined = t.thread_id || undefined;
        if (!threadId) {
          const post = await board.createForumPost(env, t).catch(() => null);
          if (post?.thread_id) {
            threadId = post.thread_id;
            await adminApi.setTicketThread(env, t.id, threadId).catch(() => {});
          }
        } else {
          await board.moveForumPost(env, threadId, t, col, "LP_Bot").catch(() => {});
        }
        await refreshPublishedDashboard(env).catch(() => {});
        return `Ticket ${t.id} -> ${col}`;
      }
      case "list_leads": {
        const rows = await db.listLeads(env, args.status);
        return rows.length ? j(rows) : "No leads in the pipeline yet.";
      }
      case "save_lead": {
        const joined = `${args.name || ""} ${args.contact || ""} ${args.source || ""}`.toLowerCase();
        if (!args.contact && /example\.com|potential lead|web_search_result|placeholder|unknown/.test(joined)) {
          return "Lead not saved: this looks like a placeholder, not a real lead with contact/source evidence.";
        }
        const l = await db.saveLead(env, args.name, args.contact, args.source, args.summary, Number(args.score || 0));
        return `Saved lead #${l.id}: ${l.name} (score ${l.score}, status ${l.status})`;
      }
      case "update_lead_status": {
        const l = await db.updateLeadStatus(env, Number(args.id), args.status);
        return l ? `Lead #${l.id} -> ${l.status}` : `No lead with id ${args.id}.`;
      }
      case "log_expense": {
        const e = await db.logExpense(env, Number(args.amount), args.category, args.vertical, args.note);
        return `Logged expense #${e.id}: $${e.amount} (${e.category || "uncategorised"})`;
      }
      case "get_expense_summary": {
        const s = await db.expenseSummary(env, Number(args.days || 30));
        const breakdown = s.byCategory.map((c: any) => `${c.category || "uncategorised"}: $${Number(c.total).toFixed(2)}`).join(", ");
        return `Total spend (${args.days || 30}d): $${s.total.toFixed(2)}. By category: ${breakdown || "none"}.`;
      }
      case "ask_business_brain": {
        const knowledge = await db.getCompanyKnowledge(env);
        const sys = `You are the LaunchPixel Business Brain. You know the company's SOPs, KPIs, positioning and rules. Answer from this knowledge; if it isn't covered, say so plainly.\n\n${knowledge}`;
        return (await geminiText(env, sys, args.query)) || "(no answer)";
      }
      case "learn_business_rule": {
        await db.upsertCompanyKnowledge(env, args.topic, args.content);
        return `Saved business knowledge under topic: ${args.topic}`;
      }
      case "list_decisions": {
        const rows = await db.listDecisions(env, Number(args.limit || 10));
        return rows.length ? j(rows.map((r) => ({ id: r.id, q: r.question, verdict: (r.verdict || "").slice(0, 200) }))) : "No decisions logged yet.";
      }
      case "escalate_to_founder": {
        const a = await db.recordAlert(env, args.severity || "medium", args.topic, args.summary);
        if (a.duplicate) return `Escalation already exists from the last 24h (#${a.id}, ${a.severity}); not posting a duplicate.`;
        return `Escalation #${a.id} recorded (${a.severity}). It will be delivered to the founder on the next tick.`;
      }
      case "web_search":
        return await webSearch(args.query);
      case "consult_council": {
        const verdict = await consultCouncil(env, String(args.decision || ""), String(args.context || ""));
        return verdict || "(council returned no verdict)";
      }
      default:
        return `Unknown tool: ${name}`;
    }
  } catch (e: any) {
    return `Tool error in ${name}: ${e?.message || String(e)}`;
  }
}

// Best-effort DuckDuckGo Lite scrape (no API key). Degrades gracefully.
async function webSearch(query: string): Promise<string> {
  try {
    const res = await fetch("https://lite.duckduckgo.com/lite/?q=" + encodeURIComponent(query), {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; LP_Bot/1.0)" },
    });
    const html = await res.text();
    const results: string[] = [];
    const re = /<a[^>]*class="result-link"[^>]*>(.*?)<\/a>/gis;
    let m: RegExpExecArray | null;
    while ((m = re.exec(html)) && results.length < 5) {
      const title = m[1].replace(/<[^>]+>/g, "").trim();
      if (title) results.push("• " + title);
    }
    if (!results.length) {
      const snip = /<td[^>]*class="result-snippet"[^>]*>(.*?)<\/td>/gis;
      while ((m = snip.exec(html)) && results.length < 5) {
        const s = m[1].replace(/<[^>]+>/g, "").trim();
        if (s) results.push("• " + s.slice(0, 200));
      }
    }
    return results.length ? `Web results for "${query}":\n${results.join("\n")}` : `No web results parsed for "${query}".`;
  } catch (e: any) {
    return `web_search unavailable: ${e?.message || e}`;
  }
}
