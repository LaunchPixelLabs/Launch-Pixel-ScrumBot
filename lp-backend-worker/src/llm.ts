// Low-level LLM transport for the brains, over plain fetch().
//
//  * Lead brain  : Google Gemini (PRIMARY_MODEL, e.g. gemini-3.5-flash)
//  * Fast brain  : Groq (GROQ_MODEL, e.g. openai/gpt-oss-120b)
//  * Backup brain: NVIDIA NIM (SECONDARY_MODEL, e.g. meta/llama-3.1-8b-instruct)
//
// No LangChain: on the edge, direct fetch is smaller, faster to cold-start and
// gives us full control over Gemini-3's tool-call `thoughtSignature` handling.
import { Env } from "./types";

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";
const GROQ_BASE = "https://api.groq.com/openai/v1";
const NIM_BASE = "https://integrate.api.nvidia.com/v1";

const RETRYABLE = new Set([408, 409, 425, 429, 500, 502, 503, 504]);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function fetchJson(url: string, init: RequestInit, tries = 3): Promise<any> {
  let lastErr: any;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url, init);
      if (res.ok) return await res.json();
      const body = await res.text();
      if (RETRYABLE.has(res.status) && i < tries - 1) {
        await sleep(600 * (i + 1) + Math.floor(Math.random() * 400));
        continue;
      }
      throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`);
    } catch (e) {
      lastErr = e;
      if (i < tries - 1) await sleep(500 * (i + 1));
    }
  }
  throw lastErr;
}

// --- Gemini (lead) ---------------------------------------------------------

export interface GeminiCall {
  system?: string;
  contents: any[]; // Gemini-native Content[]
  tools?: { functionDeclarations: any[] }[];
  temperature?: number;
}

// If the pinned model is ever retired (the 404 that started this whole saga),
// fall through to the rolling alias so the strong brain stays up instead of
// silently degrading to the weaker NIM second brain.
const GEMINI_FALLBACK = "gemini-flash-latest";
const isModelGone = (msg: string) => /HTTP 404|not found|no longer available|is not supported/i.test(msg);

/** One Gemini turn. Returns the raw model `content` (parts array) so the caller
 *  can echo it back verbatim — Gemini 3 requires the tool-call `thoughtSignature`
 *  to be preserved across turns. */
export async function callGemini(env: Env, call: GeminiCall): Promise<{ content: any; text: string; finishReason: string }> {
  const base = env.GEMINI_BASE_URL || GEMINI_BASE;
  const body: any = {
    contents: call.contents,
    generationConfig: { temperature: call.temperature ?? 0.3 },
  };
  if (call.system) body.systemInstruction = { parts: [{ text: call.system }] };
  if (call.tools && call.tools.length) body.tools = call.tools;

  const primary = env.PRIMARY_MODEL || "gemini-3.5-flash";
  const models = primary === GEMINI_FALLBACK ? [primary] : [primary, GEMINI_FALLBACK];
  let lastErr: any;
  for (const model of models) {
    try {
      const url = `${base}/models/${model}:generateContent?key=${env.GEMINI_API_KEY}`;
      const data = await fetchJson(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const cand = data?.candidates?.[0];
      const content = cand?.content ?? { role: "model", parts: [] };
      const parts = content.parts || [];
      const text = parts.filter((p: any) => typeof p.text === "string").map((p: any) => p.text).join("");
      return { content, text, finishReason: cand?.finishReason || "STOP" };
    } catch (e: any) {
      lastErr = e;
      // Only swap models when THIS model is gone; for quota/network errors
      // rethrow so the agent's NIM fallback takes over instead.
      if (!isModelGone(String(e?.message || e))) throw e;
      console.warn(`Gemini model '${model}' unavailable, trying next.`);
    }
  }
  throw lastErr;
}

export async function geminiText(env: Env, system: string, prompt: string): Promise<string> {
  const { text } = await callGemini(env, { system, contents: [{ role: "user", parts: [{ text: prompt }] }] });
  return (text || "").trim();
}

// --- OpenAI-compatible chat providers -------------------------------------

export interface OpenAIChatCall {
  messages: any[]; // OpenAI-native messages
  tools?: any[];
  temperature?: number;
  key?: string;
  model?: string;
  baseUrl?: string;
  maxTokens?: number;
  disableParallelTools?: boolean;
}

async function callOpenAICompat(call: OpenAIChatCall): Promise<any> {
  const body: any = {
    model: call.model,
    messages: call.messages,
    temperature: call.temperature ?? 0.3,
    max_tokens: call.maxTokens || 1400,
  };
  if (call.tools && call.tools.length) {
    body.tools = call.tools;
    body.tool_choice = "auto";
    body.parallel_tool_calls = call.disableParallelTools ? false : true;
  }
  const data = await fetchJson(`${call.baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${call.key}`,
    },
    body: JSON.stringify(body),
  });
  return data?.choices?.[0]?.message ?? { role: "assistant", content: "" };
}

// --- Groq (fast brain) -----------------------------------------------------

export function groqKey(env: Env): string {
  return env.GROQ_API_KEY || env.groq_api_key || "";
}

export async function callGroq(env: Env, call: OpenAIChatCall): Promise<any> {
  const key = call.key || groqKey(env);
  if (!key) throw new Error("GROQ_API_KEY is not configured");
  return callOpenAICompat({
    ...call,
    key,
    model: call.model || env.GROQ_MODEL || "openai/gpt-oss-120b",
    baseUrl: call.baseUrl || GROQ_BASE,
    disableParallelTools: true,
  });
}

export async function groqText(env: Env, system: string, prompt: string): Promise<string> {
  const msg = await callGroq(env, {
    messages: [
      { role: "system", content: system },
      { role: "user", content: prompt },
    ],
  });
  return (msg?.content || "").trim();
}

// --- NVIDIA NIM (backup) ---------------------------------------------------

export async function callNim(env: Env, call: OpenAIChatCall): Promise<any> {
  return callOpenAICompat({
    ...call,
    key: call.key || env.NVIDIA_API_KEY,
    model: call.model || env.SECONDARY_MODEL || "meta/llama-3.1-8b-instruct",
    baseUrl: call.baseUrl || env.NIM_BASE_URL || NIM_BASE,
    disableParallelTools: true,
  });
}

export async function nimText(env: Env, system: string, prompt: string): Promise<string> {
  const msg = await callNim(env, {
    messages: [
      { role: "system", content: system },
      { role: "user", content: prompt },
    ],
  });
  return (msg?.content || "").trim();
}
