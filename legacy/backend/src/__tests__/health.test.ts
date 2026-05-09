import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { buildApp } from '../app.js'

let app: FastifyInstance

beforeAll(async () => {
  process.env.AUTH_BYPASS = 'true'
  app = await buildApp()
  await app.ready()
})

afterAll(async () => {
  await app.close()
})

describe('GET /health', () => {
  it('returns 200 with status ok', async () => {
    const res = await app.inject({ method: 'GET', url: '/health' })
    expect(res.statusCode).toBe(200)
    const body = res.json<{ status: string; ts: string }>()
    expect(body.status).toBe('ok')
    expect(typeof body.ts).toBe('string')
  })

  it('does not require authorization', async () => {
    const res = await app.inject({ method: 'GET', url: '/health' })
    expect(res.statusCode).not.toBe(401)
  })
})
