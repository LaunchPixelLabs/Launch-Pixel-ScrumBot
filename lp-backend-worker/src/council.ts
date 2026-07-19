// The Dual-Brain council for high-stakes decisions: both brains answer
// independently, then the lead brain (Gemini) synthesises a weighted verdict.
// Every deliberation is logged to the `decisions` table so the council has a
// memory and can stay consistent (list_decisions).
import { Env } from "./types";
import { geminiText, groqKey, groqText, nimText } from "./llm";
import { recordDecision } from "./db";

const BASE = "You are a decision-making brain for LaunchPixel (launchpixel.in), an elite product/development agency. Be decisive, concrete and honest about trade-offs and risk.";

export async function consultCouncil(env: Env, question: string, context = ""): Promise<string> {
  const ctx = context ? `${BASE}\n\nRelevant context:\n${context}` : BASE;

  let leadAns = "";
  let secondAns = "";
  try {
    [leadAns, secondAns] = await Promise.all([
      geminiText(env, `${ctx}\n\nYou are the LEAD brain.`, question),
      (groqKey(env)
        ? groqText(env, `${ctx}\n\nYou are the FAST SECOND-OPINION brain.`, question)
        : nimText(env, `${ctx}\n\nYou are the SECOND-OPINION brain.`, question)
      ).catch(() => nimText(env, `${ctx}\n\nYou are the BACKUP SECOND-OPINION brain.`, question).catch(() => "")),
    ]);
  } catch (e: any) {
    // Gemini down: run single-brain on Groq first, then NIM.
    const only = await (groqKey(env) ? groqText(env, ctx, question).catch(() => nimText(env, ctx, question)) : nimText(env, ctx, question)).catch((err) => `(no answer — ${err?.message || err})`);
    await recordDecision(env, question, only, "(lead brain unavailable)", only).catch(() => {});
    return only;
  }

  if (!secondAns) {
    await recordDecision(env, question, leadAns, "(no second opinion)", leadAns).catch(() => {});
    return leadAns;
  }

  const secondName = groqKey(env) ? "Groq" : "NVIDIA NIM";
  const synthesis = `Decision to make:\n${question}\n\n--- Gemini (lead, 51%) said ---\n${leadAns}\n\n--- ${secondName} (second opinion, 49%) said ---\n${secondAns}\n\nAs the lead brain, deliver the FINAL decision. Weight your own view at 51% and the second opinion at 49%, but genuinely fold in anything the second brain raised that you missed. Respond with:\n1. **Decision:** one clear line.\n2. **Why:** 2-3 sentences.\n3. **Consensus:** state whether both brains agreed, or where they diverged and why you ruled the way you did.\nKeep it tight and use Discord markdown.`;

  let verdict = "";
  try {
    verdict = await geminiText(env, `${ctx}\n\nYou are the LEAD brain making the final call.`, synthesis);
  } catch {
    verdict = leadAns; // fall back to the lead's raw answer
  }
  await recordDecision(env, question, leadAns, secondAns, verdict).catch(() => {});
  return verdict;
}
