// Shared types + the Cloudflare environment binding for LP_Bot.
//
// We keep a tiny set of ambient Cloudflare types here instead of pulling in
// @cloudflare/workers-types, so the Worker stays dependency-light and bundles
// cleanly with wrangler/esbuild.

export interface KVNamespace {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, opts?: { expirationTtl?: number }): Promise<void>;
  delete(key: string): Promise<void>;
}

export interface ExecutionContext {
  waitUntil(promise: Promise<any>): void;
  passThroughOnException(): void;
}

export interface ScheduledController {
  scheduledTime: number;
  cron: string;
}

/** All bindings LP_Bot needs. Secrets are set via `wrangler secret put`; the
 *  rest are plain `[vars]` in wrangler.toml. */
export interface Env {
  // --- Secrets ---
  DISCORD_TOKEN: string;          // Bot token (REST + command registration)
  DISCORD_PUBLIC_KEY: string;     // Ed25519 key for interaction verification
  GEMINI_API_KEY: string;         // Lead brain
  GROQ_API_KEY?: string;          // Fast OpenAI-compatible brain
  groq_api_key?: string;          // Local .env compatibility; Cloudflare secret should be GROQ_API_KEY
  NVIDIA_API_KEY: string;         // Second brain (NVIDIA NIM)
  NVIDIA2_API_KEY?: string;       // Optional backup NIM key
  DATABASE_URL: string;           // Neon Postgres
  COMPOSIO_API_KEY?: string;      // Reserved for the Composio follow-up
  ADMIN_API_KEY: string;          // Auth for Admin's bot-facing task API (matches Admin's LP_BOT_API_KEY)

  // --- Vars ---
  APPLICATION_ID: string;
  ADMIN_API_BASE_URL: string;     // Base URL of the Admin dashboard (e.g. https://admin.launchpixel.in) — source of truth for kanban/task data
  PRIMARY_MODEL: string;          // e.g. gemini-3.5-flash
  GROQ_MODEL?: string;            // e.g. openai/gpt-oss-120b
  SECONDARY_MODEL: string;        // e.g. meta/llama-3.1-8b-instruct
  GEMINI_BASE_URL?: string;
  NIM_BASE_URL?: string;
  AUTONOMOUS_CHANNEL_ID?: string; // default home for the 24/7 loop (#exec-boardroom)
  STANDUP_CHANNEL_ID?: string;    // accountability focus (#daily-standup-logs)
  AI_CHANNEL_ID?: string;         // knowledge/learning focus (#ai-intern)
  LEADS_CHANNEL_ID?: string;      // leads focus (optional dedicated channel)
  INCIDENTS_CHANNEL_ID?: string;  // high/critical escalations (#incident-alerts)
  BLOCKERS_CHANNEL_ID?: string;   // medium escalations (#blocker-resolution)
  FOUNDER_DISCORD_ID?: string;    // @mention + DM target for escalations
  WHATSAPP_VERIFY_TOKEN?: string;
  DISCORD_WHATSAPP_WEBHOOK_URL?: string;
  DISCORD_GUILD_ID?: string; // Used for web-board links back to Discord threads
  PUBLIC_BOARD_URL?: string; // Public URL returned by /devops
  BOARD_ADMIN_TOKEN?: string; // Optional write guard for the browser board
  KANBAN_FORUM_CHANNEL_ID?: string; // #kanban-board forum channel — 1 ticket = 1 post, tag = column
  KANBAN_DASHBOARD_CHANNEL_ID?: string; // Text channel for the persistent Azure-style board dashboard

  // --- KV (autonomous loop state) ---
  LP_STATE: KVNamespace;
}

// --- Provider-neutral chat primitives -------------------------------------

export type Role = "system" | "user" | "assistant" | "tool";

/** A minimal history turn (final text only; no tool calls persisted). */
export interface Turn {
  role: "user" | "assistant";
  content: string;
}

export interface ToolSchema {
  name: string;
  description: string;
  parameters: Record<string, any>; // JSON Schema object
}
