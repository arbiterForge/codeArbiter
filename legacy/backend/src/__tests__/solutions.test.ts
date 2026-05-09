import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import type { FastifyInstance } from 'fastify'

// Mock DB before app import so routes use the stub
vi.mock('../db/index.js', () => ({
  db: {
    select: vi.fn(),
  },
}))

import { buildApp } from '../app.js'
import { db } from '../db/index.js'

const mockSelect = vi.mocked(db.select)

const SOLUTION_ROW = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'Alpha Suite',
  version: '1.0.0',
  maturity: 'mvp' as const,
  description: 'First solution',
  graph: { nodes: [], adapters: [] },
  createdAt: new Date('2024-01-01T00:00:00Z'),
  updatedAt: new Date('2024-01-01T00:00:00Z'),
}

let app: FastifyInstance

beforeAll(async () => {
  process.env.AUTH_BYPASS = 'true'
  app = await buildApp()
  await app.ready()
})

afterAll(async () => {
  await app.close()
})

describe('GET /api/v1/solutions', () => {
  it('returns 200 with solution list', async () => {
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        orderBy: vi.fn().mockResolvedValue([SOLUTION_ROW]),
      }),
    } as never)

    const res = await app.inject({ method: 'GET', url: '/api/v1/solutions' })
    expect(res.statusCode).toBe(200)
    const body = res.json<unknown[]>()
    expect(Array.isArray(body)).toBe(true)
    expect(body).toHaveLength(1)
  })

  it('returns 401 when no token and bypass is off', async () => {
    process.env.AUTH_BYPASS = 'false'
    const isolated = await buildApp()
    await isolated.ready()

    const res = await isolated.inject({ method: 'GET', url: '/api/v1/solutions' })
    expect(res.statusCode).toBe(401)
    await isolated.close()
    process.env.AUTH_BYPASS = 'true'
  })

  it('returns empty array when no solutions exist', async () => {
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        orderBy: vi.fn().mockResolvedValue([]),
      }),
    } as never)

    const res = await app.inject({ method: 'GET', url: '/api/v1/solutions' })
    expect(res.statusCode).toBe(200)
    expect(res.json()).toEqual([])
  })
})

describe('GET /api/v1/solutions/:id', () => {
  it('returns 200 with solution detail including graph', async () => {
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          limit: vi.fn().mockResolvedValue([SOLUTION_ROW]),
        }),
      }),
    } as never)

    const res = await app.inject({
      method: 'GET',
      url: `/api/v1/solutions/${SOLUTION_ROW.id}`,
    })
    expect(res.statusCode).toBe(200)
    const body = res.json<{ id: string; graph: unknown }>()
    expect(body.id).toBe(SOLUTION_ROW.id)
    expect(body.graph).toBeDefined()
  })

  it('returns 404 when solution does not exist', async () => {
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          limit: vi.fn().mockResolvedValue([]),
        }),
      }),
    } as never)

    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/solutions/00000000-0000-0000-0000-000000000000',
    })
    expect(res.statusCode).toBe(404)
  })
})
