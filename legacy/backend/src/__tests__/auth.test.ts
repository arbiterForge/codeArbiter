import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest'
import type { FastifyInstance } from 'fastify'

// Mocks MUST be declared before any imports that transitively load the mocked modules.
vi.mock('jose', () => ({
  createRemoteJWKSet: vi.fn().mockReturnValue({}),
  jwtVerify: vi.fn(),
}))

vi.mock('../lib/audit/index.js', () => ({
  emit: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../db/index.js', () => ({
  db: {
    select: vi.fn().mockReturnValue({
      from: vi.fn().mockReturnValue({
        orderBy: vi.fn().mockResolvedValue([]),
      }),
    }),
  },
}))

import { buildApp } from '../app.js'
import { jwtVerify } from 'jose'
import { emit } from '../lib/audit/index.js'

const mockJwtVerify = vi.mocked(jwtVerify)
const mockEmit = vi.mocked(emit)

let app: FastifyInstance

beforeAll(async () => {
  delete process.env.AUTH_BYPASS
  process.env.OIDC_JWKS_URI = 'https://oidc.test/jwks'
  process.env.OIDC_ISSUER = 'https://oidc.test'
  app = await buildApp()
  await app.ready()
})

afterAll(async () => {
  await app.close()
  delete process.env.OIDC_JWKS_URI
  delete process.env.OIDC_ISSUER
})

beforeEach(() => {
  mockEmit.mockClear()
  mockJwtVerify.mockClear()
})

describe('verifyToken — authn.success audit event', () => {
  it('emits authn.success with all required fields on valid token', async () => {
    mockJwtVerify.mockResolvedValue({ payload: { sub: 'user-abc-123' }, protectedHeader: {} } as never)

    await app.inject({
      method: 'GET',
      url: '/api/v1/solutions',
      headers: { Authorization: 'Bearer valid.jwt.token' },
    })
    await new Promise((r) => setTimeout(r, 0))

    expect(mockEmit).toHaveBeenCalledOnce()
    const event = mockEmit.mock.calls[0]?.[0]
    expect(event?.action).toBe('authn.success')
    expect(event?.outcome).toBe('success')
    expect(event?.actor.id).toBe('user-abc-123')
    expect(event?.actor.type).toBe('user')
    expect(event?.subject.type).toBeDefined()
    expect(event?.subject.id).toBeDefined()
    expect(event?.source.request_id).toBeDefined()
    expect(event?.classification).toBe('none')
    expect(event?.metadata.schema_version).toBe('1.0.0')
    expect(event?.metadata.product).toBe('fusion-core')
    expect(event?.ts).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)
    expect(event?.event_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
  })
})

describe('verifyToken — authn.failure audit event', () => {
  it('emits authn.failure with reason on invalid token', async () => {
    mockJwtVerify.mockRejectedValue(new Error('jwt expired'))

    await app.inject({
      method: 'GET',
      url: '/api/v1/solutions',
      headers: { Authorization: 'Bearer expired.jwt.token' },
    })
    await new Promise((r) => setTimeout(r, 0))

    expect(mockEmit).toHaveBeenCalledOnce()
    const event = mockEmit.mock.calls[0]?.[0]
    expect(event?.action).toBe('authn.failure')
    expect(event?.outcome).toBe('failure')
    expect(event?.actor.id).toBe('anonymous')
    expect(event?.actor.type).toBe('user')
    expect(event?.reason).toBe('invalid_token')
    expect(event?.source.request_id).toBeDefined()
    expect(event?.metadata.schema_version).toBe('1.0.0')
    expect(event?.metadata.product).toBe('fusion-core')
  })

  it('emits authn.failure with reason on missing Authorization header', async () => {
    await app.inject({ method: 'GET', url: '/api/v1/solutions' })
    await new Promise((r) => setTimeout(r, 0))

    expect(mockEmit).toHaveBeenCalledOnce()
    const event = mockEmit.mock.calls[0]?.[0]
    expect(event?.action).toBe('authn.failure')
    expect(event?.outcome).toBe('failure')
    expect(event?.actor.id).toBe('anonymous')
    expect(event?.reason).toBe('missing_token')
  })

  it('returns 401 on missing token', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/v1/solutions' })
    expect(res.statusCode).toBe(401)
    expect(res.json<{ error: string }>().error).toBe('missing_token')
  })

  it('returns 401 on invalid token', async () => {
    mockJwtVerify.mockRejectedValue(new Error('invalid'))
    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/solutions',
      headers: { Authorization: 'Bearer bad' },
    })
    expect(res.statusCode).toBe(401)
    expect(res.json<{ error: string }>().error).toBe('invalid_token')
  })
})

describe('verifyToken — no audit event on public paths', () => {
  it('does not emit for GET /health', async () => {
    await app.inject({ method: 'GET', url: '/health' })
    await new Promise((r) => setTimeout(r, 0))
    expect(mockEmit).not.toHaveBeenCalled()
  })
})
