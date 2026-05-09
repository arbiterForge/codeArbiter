import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import type { FastifyInstance } from 'fastify'

vi.mock('../db/index.js', () => ({
  db: {
    select: vi.fn(),
    insert: vi.fn(),
  },
}))

vi.mock('../lib/audit/index.js', () => ({
  emit: vi.fn().mockResolvedValue(undefined),
}))

import { buildApp } from '../app.js'
import { db } from '../db/index.js'
import { emit } from '../lib/audit/index.js'

const mockSelect = vi.mocked(db.select)
const mockInsert = vi.mocked(db.insert)
const mockEmit = vi.mocked(emit)

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

const VALID_BODY = {
  classification: 'none',
  deploymentTarget: 'on-prem',
  keycloakRealm: 'fusion',
  keycloakUrl: 'https://keycloak.example.com',
  adDomain: 'example.com',
  replicaCount: 1,
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

describe('POST /api/v1/solutions/:solutionId/deployments', () => {
  it('happy path — returns 201 with deployment record', async () => {
    const now = new Date()
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          limit: vi.fn().mockResolvedValue([SOLUTION_ROW]),
        }),
      }),
    } as never)
    mockInsert.mockReturnValue({
      values: vi.fn().mockReturnValue({
        returning: vi.fn().mockResolvedValue([
          {
            id: '22222222-2222-2222-2222-222222222222',
            solutionId: SOLUTION_ROW.id,
            solutionName: SOLUTION_ROW.name,
            status: 'queued',
            actorSub: 'bypass-user',
            classification: 'none',
            replicaCount: 1,
            createdAt: now,
            updatedAt: now,
          },
        ]),
      }),
    } as never)

    const res = await app.inject({
      method: 'POST',
      url: `/api/v1/solutions/${SOLUTION_ROW.id}/deployments`,
      payload: VALID_BODY,
    })
    expect(res.statusCode).toBe(201)
    const body = res.json<{ status: string; solutionId: string }>()
    expect(body.status).toBe('queued')
    expect(body.solutionId).toBe(SOLUTION_ROW.id)
  })

  it('emits deploy.solution audit event on success', async () => {
    mockEmit.mockClear()
    const now = new Date()
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          limit: vi.fn().mockResolvedValue([SOLUTION_ROW]),
        }),
      }),
    } as never)
    mockInsert.mockReturnValue({
      values: vi.fn().mockReturnValue({
        returning: vi.fn().mockResolvedValue([
          {
            id: '33333333-3333-3333-3333-333333333333',
            solutionId: SOLUTION_ROW.id,
            solutionName: SOLUTION_ROW.name,
            status: 'queued',
            actorSub: 'bypass-user',
            classification: 'none',
            replicaCount: 1,
            createdAt: now,
            updatedAt: now,
          },
        ]),
      }),
    } as never)

    await app.inject({
      method: 'POST',
      url: `/api/v1/solutions/${SOLUTION_ROW.id}/deployments`,
      payload: VALID_BODY,
    })

    // Flush the fire-and-forget emit promise
    await new Promise((r) => setTimeout(r, 0))

    expect(mockEmit).toHaveBeenCalledOnce()
    const event = mockEmit.mock.calls[0]?.[0]
    // Always-required fields (F-002: full schema field assertions)
    expect(event?.action).toBe('deploy.solution')
    expect(event?.outcome).toBe('success')
    expect(event?.actor.id).toBe('bypass-user')
    expect(event?.actor.type).toBeDefined()
    expect(event?.subject.type).toBeDefined()
    expect(event?.subject.id).toBeDefined()
    expect(event?.source.request_id).toBeDefined()
    expect(event?.classification).toBeDefined()
    expect(event?.metadata.schema_version).toBe('1.0.0')
    expect(event?.metadata.product).toBe('fusion-core')
    expect(event?.ts).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)
    expect(event?.event_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
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
      method: 'POST',
      url: '/api/v1/solutions/00000000-0000-0000-0000-000000000000/deployments',
      payload: VALID_BODY,
    })
    expect(res.statusCode).toBe(404)
  })

  it('returns 422 on invalid body — missing keycloakRealm', async () => {
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          limit: vi.fn().mockResolvedValue([SOLUTION_ROW]),
        }),
      }),
    } as never)

    const res = await app.inject({
      method: 'POST',
      url: `/api/v1/solutions/${SOLUTION_ROW.id}/deployments`,
      payload: { ...VALID_BODY, keycloakRealm: '' },
    })
    expect(res.statusCode).toBe(422)
  })

  it('returns 422 on invalid body — replicaCount out of range', async () => {
    mockSelect.mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockReturnValue({
          limit: vi.fn().mockResolvedValue([SOLUTION_ROW]),
        }),
      }),
    } as never)

    const res = await app.inject({
      method: 'POST',
      url: `/api/v1/solutions/${SOLUTION_ROW.id}/deployments`,
      payload: { ...VALID_BODY, replicaCount: 10 },
    })
    expect(res.statusCode).toBe(422)
  })

  it('returns 401 when no token and bypass is off', async () => {
    process.env.AUTH_BYPASS = 'false'
    const isolated = await buildApp()
    await isolated.ready()

    const res = await isolated.inject({
      method: 'POST',
      url: `/api/v1/solutions/${SOLUTION_ROW.id}/deployments`,
      payload: VALID_BODY,
    })
    expect(res.statusCode).toBe(401)
    await isolated.close()
    process.env.AUTH_BYPASS = 'true'
  })
})
