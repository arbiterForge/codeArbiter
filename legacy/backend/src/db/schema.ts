import { pgTable, text, timestamp, integer, jsonb } from 'drizzle-orm/pg-core'

// classification: none — solutions catalog metadata is unclassified at S1
export const solutions = pgTable('solutions', {
  id: text('id').primaryKey(),
  name: text('name').notNull(),
  version: text('version').notNull(),
  maturity: text('maturity', { enum: ['prototype', 'mvp', 'production'] }).notNull(),
  description: text('description').notNull(),
  // graph stored as JSONB — typed at application layer via Zod
  graph: jsonb('graph').notNull().$type<{ nodes: unknown[]; adapters: unknown[] }>(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
})

// classification: none — deployment records at S1 contain no CUI
export const deployments = pgTable('deployments', {
  id: text('id').primaryKey(),
  solutionId: text('solution_id')
    .notNull()
    .references(() => solutions.id),
  solutionName: text('solution_name').notNull(),
  status: text('status', {
    enum: ['queued', 'provisioning', 'configuring', 'verifying', 'success', 'failed'],
  }).notNull(),
  actorSub: text('actor_sub').notNull(),
  classification: text('classification', { enum: ['none', 'cui', 'secret_ref'] })
    .notNull()
    .default('none'),
  replicaCount: integer('replica_count').notNull().default(1),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
})
