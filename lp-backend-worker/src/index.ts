// LP_Bot — unified Cloudflare Worker entry.
//
//   fetch()     : Discord HTTP interactions (deferred) + WhatsApp webhook + board API
//   scheduled() : the 24/7 autonomous Scrum-Master shift (Cron Trigger)
//
// Discord interactions MUST be answered within 3s, so every slash command is
// acknowledged immediately with a "deferred" response (type 5) and the real
// work runs in ctx.waitUntil(), editing the message when it's ready. That is
// the fix for the old "The application did not respond" errors.
import { Hono } from "hono";
import { verifyKey } from "discord-interactions";
import { Env, ScheduledController, ExecutionContext } from "./types";
import { handleCommand, handleComponent } from "./commands";
import { editInteraction } from "./discord";
import { runAutonomousCycle } from "./autonomous";

const app = new Hono<{ Bindings: Env }>();
const API_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Board-Token",
  "Cache-Control": "no-store",
};

app.get("/", (c) => c.text("🚀 LP_Bot edge is online. Discord interactions: POST /interactions"));
app.get("/health", (c) => c.json({ ok: true, bot: "LP_Bot", ts: Date.now() }));

// The old hand-rolled board page is retired — Admin now owns the Kanban UI
// (with real session/OTP auth, unlike this page's easily-guessable write token).
app.get("/devops-board", (c) => c.redirect(`${(c.env.ADMIN_API_BASE_URL || "").replace(/\/+$/, "")}/admin/devops-board`, 302));

// --- Retired board web app API ---------------------------------------------
// Board data now lives in Admin's Postgres and is served by Admin's own API +
// UI. These routes used to read/write LP_Bot's local `tickets` table directly;
// keep them responding (410) instead of silently 404ing so old bookmarks/API
// callers get pointed at the new home instead of two competing board UIs.
app.options("/api/*", () => new Response(null, { status: 204, headers: API_HEADERS }));

const boardRetired = (c: any) =>
  json(
    c,
    {
      error: "This board API has been retired. Board data now lives in the Admin dashboard.",
      board_url: `${(c.env.ADMIN_API_BASE_URL || "").replace(/\/+$/, "")}/admin/devops-board`,
    },
    410
  );

app.get("/api/board", boardRetired);
app.get("/api/tickets/:id", boardRetired);
app.post("/api/tickets", boardRetired);
app.patch("/api/tickets/:id", boardRetired);

// --- Discord interactions --------------------------------------------------
app.post("/interactions", async (c) => {
  const sig = c.req.header("x-signature-ed25519");
  const ts = c.req.header("x-signature-timestamp");
  const raw = await c.req.text();

  if (!sig || !ts || !c.env.DISCORD_PUBLIC_KEY) return c.text("missing signature", 401);
  const valid = await verifyKey(raw, sig, ts, c.env.DISCORD_PUBLIC_KEY);
  if (!valid) return c.text("bad signature", 401);

  const body = JSON.parse(raw);

  // PING
  if (body.type === 1) return c.json({ type: 1 });

  // APPLICATION_COMMAND
  if (body.type === 2) {
    const name: string = body.data?.name;
    const user = body.member?.user || body.user || {};
    const userId = user.id || "unknown";
    const userName = user.global_name || user.username || "Team Member";

    const opts: Record<string, any> = {};
    for (const o of body.data?.options || []) opts[o.name] = o.value;

    // Do the slow work after acknowledging, then edit the original message.
    c.executionCtx.waitUntil(
      (async () => {
        try {
          const reply = await handleCommand(c.env, name, opts, userId, userName, body.channel_id);
          await editInteraction(c.env, body.token, reply);
        } catch (e: any) {
          console.error("command failed:", e?.message || e);
          await editInteraction(c.env, body.token, `⚠️ Something went wrong: ${e?.message || e}`);
        }
      })()
    );

    // Deferred ack (type 5) — shows "LP_Bot is thinking…" instantly.
    // /devops may include a private board write token, so keep that reply ephemeral.
    return c.json(name === "devops" ? { type: 5, data: { flags: 64 } } : { type: 5 });
  }

  // MESSAGE_COMPONENT
  if (body.type === 3) {
    const user = body.member?.user || body.user || {};
    const userId = user.id || "unknown";
    const userName = user.global_name || user.username || "Team Member";

    c.executionCtx.waitUntil(
      (async () => {
        try {
          const reply = await handleComponent(c.env, body, userId, userName);
          await editInteraction(c.env, body.token, reply);
        } catch (e: any) {
          console.error("component failed:", e?.message || e);
          await editInteraction(c.env, body.token, `⚠️ Could not move that card: ${e?.message || e}`);
        }
      })()
    );

    // Ephemeral deferred reply so we do not overwrite the card message itself.
    return c.json({ type: 5, data: { flags: 64 } });
  }

  return c.text("unknown interaction type", 400);
});

// --- WhatsApp webhook (ported from the old index.js) -----------------------
app.get("/webhook", (c) => {
  const mode = c.req.query("hub.mode");
  const token = c.req.query("hub.verify_token");
  const challenge = c.req.query("hub.challenge");
  if (mode === "subscribe" && token && token === c.env.WHATSAPP_VERIFY_TOKEN) {
    return c.text(challenge || "", 200);
  }
  return c.text("Forbidden", 403);
});

app.post("/webhook", async (c) => {
  const data: any = await c.req.json().catch(() => ({}));
  if (data.object === "whatsapp_business_account" && c.env.DISCORD_WHATSAPP_WEBHOOK_URL) {
    for (const entry of data.entry || []) {
      for (const change of entry.changes || []) {
        const value = change.value || {};
        for (const msg of value.messages || []) {
          const phone = msg.from || "Unknown";
          const contact = (value.contacts || [])[0];
          const senderName = contact?.profile?.name || phone;
          const text = msg.type === "text" ? msg.text?.body || "" : `[${(msg.type || "media").toUpperCase()} message]`;
          await fetch(c.env.DISCORD_WHATSAPP_WEBHOOK_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              embeds: [
                {
                  title: "💬 WhatsApp Chat Sync (Edge)",
                  description: text,
                  color: 3066993,
                  fields: [
                    { name: "From", value: senderName, inline: true },
                    { name: "Phone", value: phone, inline: true },
                  ],
                  footer: { text: "Synced via Cloudflare Workers" },
                },
              ],
            }),
          }).catch((e) => console.error("wa->discord failed", e));
        }
      }
    }
  }
  return c.json({ status: "success" });
});

// --- Legacy board API (retired — superseded by Admin's dashboard) ----------
app.get("/tickets", boardRetired);
app.post("/comments", boardRetired);
app.post("/attachments", boardRetired);

export default {
  fetch: app.fetch,
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runAutonomousCycle(env));
  },
};

function json(c: any, body: any, status = 200): Response {
  return c.json(body, status, API_HEADERS);
}
