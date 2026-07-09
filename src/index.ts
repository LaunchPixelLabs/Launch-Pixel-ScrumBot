import { Hono } from 'hono';
import { verifyKey } from 'discord-interactions';
import { ScrumMasterAgent } from './agents/ScrumMasterAgent';

// Hono provides a very fast, Web Standard router that works perfectly on Cloudflare edge
const app = new Hono<{ Bindings: Env }>();

// Define our environment variables binding interface for Cloudflare
export interface Env {
  DISCORD_PUBLIC_KEY: string;
  LLM_BASE_URL: string;
  LLM_MODEL: string;
  LLM_API_KEY: string;
  DATABASE_URL: string;
  LP_PORTAL_BASE_URL: string;
  LP_PORTAL_API_KEY: string;
}

app.post('/api/interactions', async (c) => {
  const signature = c.req.header('x-signature-ed25519');
  const timestamp = c.req.header('x-signature-timestamp');
  const bodyText = await c.req.text();

  if (!signature || !timestamp || !c.env.DISCORD_PUBLIC_KEY) {
    return c.text('Missing headers or public key', 401);
  }

  // Verify the request securely
  const isValidRequest = verifyKey(
    bodyText,
    signature,
    timestamp,
    c.env.DISCORD_PUBLIC_KEY
  );

  if (!isValidRequest) {
    return c.text('Bad request signature', 401);
  }

  const body = JSON.parse(bodyText);

  // Handle Ping from Discord
  if (body.type === 1) {
    return c.json({ type: 1 });
  }

  // Handle Application Commands
  if (body.type === 2) {
    const commandName = body.data.name;
    const userId = body.member?.user?.id || body.user?.id || 'unknown-user';
    const userName = body.member?.user?.username || body.user?.username || 'Team Member';
    
    // Inject the Cloudflare environment variables into process.env so our existing classes work without refactoring
    process.env.LLM_BASE_URL = c.env.LLM_BASE_URL;
    process.env.LLM_MODEL = c.env.LLM_MODEL;
    process.env.LLM_API_KEY = c.env.LLM_API_KEY;
    process.env.DATABASE_URL = c.env.DATABASE_URL;
    process.env.LP_PORTAL_BASE_URL = c.env.LP_PORTAL_BASE_URL;
    process.env.LP_PORTAL_API_KEY = c.env.LP_PORTAL_API_KEY;

    // Instantiate our agent
    const agent = new ScrumMasterAgent();

    try {
      if (commandName === 'ask') {
        const query = body.data.options?.find((opt: any) => opt.name === 'query')?.value || 'Hello';
        const responseText = await agent.processMessage(query, userId, userName, false);
        return c.json({
          type: 4,
          data: { content: responseText },
        });
      }

      if (commandName === 'task' || commandName === 'board') {
        const query = `Please give me a summary of the current sprint backlog and tasks.`;
        const responseText = await agent.processMessage(query, userId, userName, true);
        return c.json({
          type: 4,
          data: { content: responseText },
        });
      }

      if (commandName === 'standup') {
        const responseText = await agent.processMessage("I am starting my daily standup.", userId, userName, false);
        return c.json({
          type: 4,
          data: { content: responseText },
        });
      }

    } catch (error) {
      console.error('Error processing command:', error);
      return c.json({
        type: 4,
        data: { content: '⚠️ I encountered an error while trying to process that request on the edge. Please check logs.' },
      });
    }

    return c.json({
      type: 4,
      data: { content: `Command /${commandName} received but not fully implemented yet.` },
    });
  }

  return c.text('Unknown interaction type', 400);
});

export default app;
