// The ReAct-style tool loop. Gemini leads; Groq is the fast second brain; NIM
// remains the backup. Some OpenAI-compatible models occasionally print a tool
// call as JSON instead of returning structured tool_calls, so this loop detects
// that pattern and executes the tool instead of dumping JSON into Discord.
import { Env, Turn } from "./types";
import { callGemini, callGroq, callNim, groqKey } from "./llm";
import { TOOL_SCHEMAS, executeTool } from "./tools";

const MAX_TOOL_ROUNDS = 4;

function safeArgs(s: string): Record<string, any> {
  try {
    return s ? JSON.parse(s) : {};
  } catch {
    return {};
  }
}

function parseTextToolCall(text: string): { name: string; args: Record<string, any> } | null {
  const raw = (text || "").trim();
  if (!raw.startsWith("{") || !raw.endsWith("}")) return null;
  try {
    const parsed = JSON.parse(raw);
    const name = parsed.name || parsed.tool || parsed.function;
    const args = parsed.arguments || parsed.parameters || parsed.args || {};
    if (typeof name !== "string") return null;
    if (!TOOL_SCHEMAS.some((t) => t.name === name)) return null;
    return { name, args: typeof args === "object" && args ? args : {} };
  } catch {
    return null;
  }
}

async function runGemini(env: Env, system: string, userText: string, history: Turn[]): Promise<string> {
  const contents: any[] = [];
  for (const t of history) contents.push({ role: t.role === "assistant" ? "model" : "user", parts: [{ text: t.content }] });
  contents.push({ role: "user", parts: [{ text: userText }] });

  const tools = [{ functionDeclarations: TOOL_SCHEMAS.map((t) => ({ name: t.name, description: t.description, parameters: t.parameters })) }];

  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    const { content, text } = await callGemini(env, { system, contents, tools });
    const parts = content.parts || [];
    const calls = parts.filter((p: any) => p.functionCall).map((p: any) => p.functionCall);
    if (!calls.length) return text || "(no response)";
    // Echo the model content VERBATIM (carries Gemini-3 thoughtSignature), then
    // append the tool results as a function-response turn.
    contents.push(content);
    const respParts: any[] = [];
    for (const c of calls) {
      const result = await executeTool(env, c.name, c.args || {});
      respParts.push({ functionResponse: { name: c.name, response: { result } } });
    }
    contents.push({ role: "user", parts: respParts });
  }
  // Force a final natural-language answer with tools disabled.
  const { text } = await callGemini(env, { system, contents });
  return cleanFinalText(text);
}

type OpenAIProvider = "groq" | "nim";

async function callProvider(provider: OpenAIProvider, env: Env, payload: any): Promise<any> {
  return provider === "groq" ? callGroq(env, payload) : callNim(env, payload);
}

function cleanFinalText(text: string): string {
  const trimmed = (text || "").trim();
  if (!trimmed || trimmed === "{}" || trimmed === "[]") return "(no response)";
  return trimmed;
}

async function runOpenAIProvider(provider: OpenAIProvider, env: Env, system: string, userText: string, history: Turn[]): Promise<string> {
  const messages: any[] = [{ role: "system", content: system }];
  for (const t of history) messages.push({ role: t.role, content: t.content });
  messages.push({ role: "user", content: userText });

  const tools = TOOL_SCHEMAS.map((t) => ({ type: "function", function: { name: t.name, description: t.description, parameters: t.parameters } }));

  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    const msg = await callProvider(provider, env, { messages, tools });
    const calls = msg.tool_calls || [];
    if (!calls.length) {
      const textTool = parseTextToolCall(String(msg.content || ""));
      if (!textTool) return cleanFinalText(msg.content || "");
      const result = await executeTool(env, textTool.name, textTool.args);
      messages.push({ role: "assistant", content: `Called ${textTool.name}.` });
      messages.push({ role: "user", content: `Tool result from ${textTool.name}:\n${result}\n\nNow answer naturally for Discord. Do not print JSON.` });
      continue;
    }
    messages.push(msg);
    for (const tc of calls) {
      const result = await executeTool(env, tc.function?.name, safeArgs(tc.function?.arguments));
      messages.push({ role: "tool", tool_call_id: tc.id, content: result });
    }
  }
  const msg = await callProvider(provider, env, { messages });
  return cleanFinalText(msg.content || "");
}

async function runNim(env: Env, system: string, userText: string, history: Turn[]): Promise<string> {
  return runOpenAIProvider("nim", env, system, userText, history);
}

async function runGroq(env: Env, system: string, userText: string, history: Turn[]): Promise<string> {
  return runOpenAIProvider("groq", env, system, userText, history);
}

/** Run the agent for one instruction. Returns the final natural-language reply. */
export async function runAgent(env: Env, system: string, userText: string, history: Turn[] = []): Promise<string> {
  try {
    const reply = await runGemini(env, system, userText, history);
    if (parseTextToolCall(reply)) throw new Error("Gemini returned an unexecuted text tool call");
    return reply;
  } catch (leadErr: any) {
    console.error("Lead brain (Gemini) failed, falling back to Groq:", leadErr?.message || leadErr);
    if (groqKey(env)) {
      try {
        return await runGroq(env, system, userText, history);
      } catch (groqErr: any) {
        console.error("Fast brain (Groq) failed, falling back to NIM:", groqErr?.message || groqErr);
      }
    }
    try {
      return await runNim(env, system, userText, history);
    } catch (backupErr: any) {
      console.error("Backup brain (NIM) also failed:", backupErr?.message || backupErr);
      return "⚠️ The AI providers are unreachable right now. I kept the Discord command alive, but no brain returned a usable answer. Try again in a minute; if this repeats, check `GROQ_API_KEY`, `GEMINI_API_KEY`, and the model names.";
    }
  }
}
