export interface Ticket {
  id: string;
  title: string;
  status: string;
  assignee?: string;
  storyPoints?: number;
}

export class LaunchPixelAdapter {
  private baseUrl: string;
  private apiKey: string;

  constructor() {
    this.baseUrl = process.env.LP_PORTAL_BASE_URL || 'https://adminapi.launchpixel.in/api';
    this.apiKey = process.env.LP_PORTAL_API_KEY || '';
  }

  /**
   * Fetch all backlog resources (Epics, Features, Stories, Tasks)
   */
  async getBacklogResources(): Promise<any> {
    try {
      const response = await fetch(`${this.baseUrl}/bot/resources`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey
        }
      });

      if (!response.ok) {
        throw new Error(`LP Admin API Error: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Failed to fetch backlog resources:', error);
      throw error;
    }
  }

  /**
   * Helper to fetch active tickets for a specific assignee
   */
  async getTickets(assignee?: string): Promise<Ticket[]> {
    const resources = await this.getBacklogResources();
    const tasks = resources.tasks || [];
    
    // Map backend DevOpsTasks to our generic Ticket interface
    let tickets: Ticket[] = tasks.map((t: any) => ({
      id: `TASK-${t.id}`,
      title: t.title,
      status: t.status,
      assignee: t.assignee || 'unassigned', // Adjust based on actual DB schema
      storyPoints: t.storyPoints || 0
    }));

    if (assignee) {
      tickets = tickets.filter(t => t.assignee?.toLowerCase() === assignee.toLowerCase());
    }

    return tickets;
  }
}
