import { drizzle } from 'drizzle-orm/postgres-js'
import postgres from 'postgres'
import * as schema from './schema.js'

// SHORTCUT [S1]: single connection pool, no pooler sidecar.
// Payback trigger: Stage 3 — add PgBouncer or Neon serverless driver.
const connectionString = process.env.DATABASE_URL ?? ''

const client = postgres(connectionString, { max: 10 })

export const db = drizzle(client, { schema })
export type DB = typeof db
