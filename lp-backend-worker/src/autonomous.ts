// The 24/7 autonomous shift, driven by a Cloudflare Cron Trigger. Each tick runs
// ONE rotating focus (briefing → leads → competitive intel → ...), de-dupes
// against the report ledger so the team isn't spammed, posts anything worthwhile
// to Discord, and delivers any queued founder escalations.
import { Env } from "./types";
import { SYSTEM_PROMPT, AUTONOMOUS_FOCUS_ORDER, FOCUS_HEADERS, buildAutonomousPrompt } from "./prompts";
import { runAgent } from "./agent";
import { postToChannel, dmUser } from "./discord";
import * as db from "./db";

/** Coarse de-dup signature: first meaningful line, stripped of markdown/emoji. */
function signature(text: string): string {
  for (const raw of (text || "").split("\n")) {
    const line = raw
      .replace(/[*_`#>~]/g, "")
      .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "")
      .trim()
      .toLowerCase();
    if (line.length > 8) return line.slice(0, 120);
  }
  return (text || "").trim().slice(0, 120).toLowerCase();
}

/** Each focus posts to its natural channel; everything else lands in the
 *  exec boardroom (the AUTONOMOUS_CHANNEL_ID default). */
function channelForFocus(env: Env, focus: string): string | undefined {
  const routes: Record<string, string | undefined> = {
    accountability: env.STANDUP_CHANNEL_ID,
    knowledge_gap: env.AI_CHANNEL_ID,
    leads: env.LEADS_CHANNEL_ID,
  };
  return routes[focus] || env.AUTONOMOUS_CHANNEL_ID;
}

async function nextFocus(env: Env): Promise<string> {
  let idx = 0;
  try {
    idx = parseInt((await env.LP_STATE.get("focus_index")) || "0", 10) || 0;
  } catch {
    /* KV miss */
  }
  const focus = AUTONOMOUS_FOCUS_ORDER[idx % AUTONOMOUS_FOCUS_ORDER.length];
  try {
    await env.LP_STATE.put("focus_index", String((idx + 1) % AUTONOMOUS_FOCUS_ORDER.length));
  } catch {
    /* best-effort */
  }
  return focus;
}

export async function runAutonomousCycle(env: Env): Promise<void> {
  const focus = await nextFocus(env);
  console.log("Autonomous cycle focus:", focus);

  try {
    const reply = await runAgent(env, SYSTEM_PROMPT, buildAutonomousPrompt(focus));
    const trimmed = (reply || "").trim();

    if (trimmed && !trimmed.includes("ALL_GOOD")) {
      const sig = signature(trimmed);
      const seen = await db.recentReportSignatures(env, focus, 12).catch(() => new Set<string>());
      if (!seen.has(sig)) {
        const header = FOCUS_HEADERS[focus] || `🤖 **${focus.replace(/_/g, " ")}**`;
        const target = channelForFocus(env, focus);
        if (target) await postToChannel(env, target, `${header}\n${trimmed}`);
        await db.recordReport(env, focus, sig, trimmed).catch(() => {});
      } else {
        console.log("Autonomous report suppressed (duplicate).");
      }
    }
  } catch (e: any) {
    console.error("Autonomous cycle error:", e?.message || e);
  }

  // Always drain founder escalations, regardless of the focus outcome.
  await deliverAlerts(env).catch((e) => console.error("Alert delivery failed:", e));
}

/** Severity ladder: medium → blockers, high → incidents (+DM), critical → incidents + boardroom (+DM). */
async function deliverAlerts(env: Env): Promise<void> {
  const exec = env.AUTONOMOUS_CHANNEL_ID;
  const incidents = env.INCIDENTS_CHANNEL_ID || exec;
  const blockers = env.BLOCKERS_CHANNEL_ID || incidents;
  const mention = env.FOUNDER_DISCORD_ID ? `<@${env.FOUNDER_DISCORD_ID}> ` : "";
  const alerts = await db.undeliveredAlerts(env).catch(() => []);
  for (const a of alerts) {
    const sev = (a.severity || "medium").toLowerCase();
    const icon = { critical: "🚨", high: "⚠️", medium: "📍", low: "🔹" }[sev] || "📍";
    const body = `${icon} **Founder Escalation (${sev.toUpperCase()})** ${["high", "critical"].includes(sev) ? mention : ""}\n**${a.topic}**\n${a.summary}`;
    try {
      if (sev === "medium" && blockers) await postToChannel(env, blockers, body);
      if (["high", "critical"].includes(sev) && incidents) await postToChannel(env, incidents, body);
      if (sev === "critical" && exec) await postToChannel(env, exec, body);
      if (["high", "critical"].includes(sev) && env.FOUNDER_DISCORD_ID) {
        await dmUser(env, env.FOUNDER_DISCORD_ID, `🚨 **LaunchPixel escalation (${sev})**\n**${a.topic}**\n${a.summary}`);
      }
    } catch (e) {
      console.error("Failed to deliver alert", a.id, e);
    }
    await db.markAlertDelivered(env, a.id).catch(() => {});
  }
}
