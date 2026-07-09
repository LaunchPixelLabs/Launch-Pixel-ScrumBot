import { pgTable, text, timestamp, uuid, jsonb } from 'drizzle-orm/pg-core';

// Represents a daily standup entry
export const standups = pgTable('standups', {
  id: uuid('id').defaultRandom().primaryKey(),
  userId: text('user_id').notNull(), // Discord User ID
  userName: text('user_name').notNull(),
  date: timestamp('date').defaultNow().notNull(),
  yesterday: text('yesterday').notNull(),
  today: text('today').notNull(),
  blockers: text('blockers'),
  rawContext: jsonb('raw_context'), // Any additional data
});

// Represents the conversational memory state
export const conversationState = pgTable('conversation_state', {
  id: uuid('id').defaultRandom().primaryKey(),
  userId: text('user_id').notNull().unique(), // Discord User ID
  memory: jsonb('memory').notNull(), // Langchain message history
  lastUpdated: timestamp('last_updated').defaultNow().notNull(),
});
