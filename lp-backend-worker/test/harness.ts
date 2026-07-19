// End-to-end smoke test of LP_Bot's brain against the LIVE Gemini + NIM + Neon.
// Run: node test/out.mjs  (after esbuild bundles this).
import { runAgent } from "../src/agent";
import { companySnapshot, getCompanyKnowledge } from "../src/db";
import { consultCouncil } from "../src/council";
import { SYSTEM_PROMPT } from "../src/prompts";

const env: any = {
  GEMINI_API_KEY: process.env.GEMINI_API_KEY,
  NVIDIA_API_KEY: process.env.NVIDIA_API_KEY,
  DATABASE_URL: process.env.DATABASE_URL,
  PRIMARY_MODEL: "gemini-3.5-flash",
  SECONDARY_MODEL: "meta/llama-3.1-8b-instruct",
};

function hr(t: string) {
  console.log("\n========== " + t + " ==========");
}

(async () => {
  hr("1. DB layer: companySnapshot (real Neon)");
  console.log(await companySnapshot(env));

  hr("2. Business Brain knowledge (real Neon, 5 rows expected)");
  console.log((await getCompanyKnowledge(env)).slice(0, 400));

  hr("3. runAgent: agent tool-loop (Gemini lead -> calls company_snapshot tool)");
  console.log(
    await runAgent(
      env,
      SYSTEM_PROMPT,
      "Give me a live status snapshot of the business using company_snapshot, then name the single most important thing to focus on today. Keep it under 6 lines."
    )
  );

  hr("4. Dual-Brain council (Gemini + NIM deliberation, logs a decision)");
  console.log(await consultCouncil(env, "Should LaunchPixel raise its minimum project size to $10k? Give a crisp verdict."));

  hr("DONE");
})().catch((e) => {
  console.error("HARNESS ERROR:", e);
  process.exit(1);
});
