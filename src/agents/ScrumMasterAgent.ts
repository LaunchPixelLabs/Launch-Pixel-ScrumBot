import { ChatOpenAI } from '@langchain/openai';
import { PromptTemplate } from '@langchain/core/prompts';
import { StringOutputParser } from '@langchain/core/output_parsers';
import { SystemMessage, HumanMessage, AIMessage, BaseMessage } from '@langchain/core/messages';
import { LaunchPixelAdapter } from '../adapters/ProjectManagement/LaunchPixelAdapter';
import { eq } from 'drizzle-orm';
import { neon } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-http';
import { conversationState } from '../db/schema';

export class ScrumMasterAgent {
  private model: ChatOpenAI;
  private pmAdapter: LaunchPixelAdapter;
  private db: any;

  constructor() {
    this.model = new ChatOpenAI({
      modelName: process.env.LLM_MODEL || 'llama3-70b-8192',
      openAIApiKey: process.env.LLM_API_KEY,
      configuration: {
        baseURL: process.env.LLM_BASE_URL,
      },
    });
    this.pmAdapter = new LaunchPixelAdapter();
    
    // Initialize DB here after process.env is injected by the request handler
    const sql = neon(process.env.DATABASE_URL!);
    this.db = drizzle(sql);
  }

  /**
   * Fetches conversation history from NeonDB
   */
  private async getHistory(userId: string): Promise<BaseMessage[]> {
    const records = await this.db.select().from(conversationState).where(eq(conversationState.userId, userId));
    if (records.length === 0) return [];
    
    // Convert generic JSON to Langchain Message objects
    const memory = records[0].memory as any[];
    return memory.map(m => {
      if (m.type === 'human') return new HumanMessage(m.content);
      if (m.type === 'ai') return new AIMessage(m.content);
      return new SystemMessage(m.content);
    });
  }

  /**
   * Saves updated conversation history back to NeonDB
   */
  private async saveHistory(userId: string, messages: BaseMessage[]): Promise<void> {
    // Keep only the last 20 messages to save context space
    const recentMessages = messages.slice(-20);
    const memoryJson = recentMessages.map(m => ({
      type: m instanceof HumanMessage ? 'human' : m instanceof AIMessage ? 'ai' : 'system',
      content: m.content
    }));

    const existing = await this.db.select().from(conversationState).where(eq(conversationState.userId, userId));
    if (existing.length === 0) {
      await this.db.insert(conversationState).values({
        userId,
        memory: memoryJson
      });
    } else {
      await this.db.update(conversationState)
        .set({ memory: memoryJson, lastUpdated: new Date() })
        .where(eq(conversationState.userId, userId));
    }
  }

  /**
   * Main conversational processor
   */
  async processMessage(message: string, userId: string, userName: string, fetchBacklog: boolean = false): Promise<string> {
    
    // 1. Fetch History
    const history = await this.getHistory(userId);

    // 2. Build Context (Optionally fetch live backlog data)
    let projectContext = "No active backlog data fetched for this query.";
    if (fetchBacklog) {
      try {
        const resources = await this.pmAdapter.getBacklogResources();
        projectContext = `Current Sprint Backlog Overview: ${JSON.stringify(resources).substring(0, 2000)}... (truncated)`;
      } catch (e) {
        projectContext = "Failed to fetch backlog from LP Admin Portal.";
      }
    }

    // 3. Construct the Senior Scrum Master Persona
    const systemPrompt = new SystemMessage(
      `You are an elite, highly experienced Agile Scrum Master for the LaunchPixel team.
Your personality is professional, highly analytical, proactive, and independently capable of guiding the team.
You do not just answer questions; you identify blockers, suggest process improvements, and keep the team aligned with Agile principles.
When asked about tasks or standups, be concise but insightful. Challenge the team constructively if estimates seem off or if blockers are lingering.

Current User: ${userName} (${userId})
Project Context: ${projectContext}

Review the conversation history, then provide a highly capable, senior-level response to the user's latest message.`
    );

    const newHumanMessage = new HumanMessage(message);
    const messagesToSend = [systemPrompt, ...history, newHumanMessage];

    // 4. Invoke LLM
    const response = await this.model.invoke(messagesToSend);
    const aiMessage = new AIMessage(response.content as string);

    // 5. Save History
    await this.saveHistory(userId, [...history, newHumanMessage, aiMessage]);

    return response.content as string;
  }
}
