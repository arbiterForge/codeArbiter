import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SINK_URL = 'http://audit.internal/events'

const BASE_EVENT = {
  ts: '2024-01-01T00:00:00.000Z',
  event_id: '11111111-1111-1111-1111-111111111111',
  action: 'authn.success',
  actor: { id: 'test-user', type: 'user' as const },
  subject: { type: 'solution' as const, id: '22222222-2222-2222-2222-222222222222' },
  outcome: 'success' as const,
  source: { request_id: '33333333-3333-3333-3333-333333333333' },
  classification: 'none' as const,
  metadata: { schema_version: '1.0.0' as const, product: 'fusion-core' as const },
}

describe('audit.emit', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    process.env.AUDIT_SINK_URL = SINK_URL
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 200 }))
  })

  afterEach(() => {
    delete process.env.AUDIT_SINK_URL
    fetchSpy.mockRestore()
  })

  it('POSTs the event to the sink URL', async () => {
    const { emit } = await import('../lib/audit/index.js')
    await emit(BASE_EVENT)
    expect(fetchSpy).toHaveBeenCalledOnce()
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(SINK_URL)
    expect(init.method).toBe('POST')
  })

  it('serializes the event as JSON', async () => {
    const { emit } = await import('../lib/audit/index.js')
    await emit(BASE_EVENT)
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(init.body as string) as typeof BASE_EVENT
    expect(body.action).toBe('authn.success')
    expect(body.actor.id).toBe('test-user')
  })

  it('is a no-op when AUDIT_SINK_URL is not configured', async () => {
    delete process.env.AUDIT_SINK_URL
    const { emit } = await import('../lib/audit/index.js')
    await emit(BASE_EVENT)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('does not throw when the sink returns 500', async () => {
    fetchSpy.mockResolvedValue(new Response(null, { status: 500 }))
    const { emit } = await import('../lib/audit/index.js')
    await expect(emit(BASE_EVENT)).resolves.toBeUndefined()
  })

  it('does not throw on network error', async () => {
    fetchSpy.mockRejectedValue(new Error('network error'))
    const { emit } = await import('../lib/audit/index.js')
    await expect(emit(BASE_EVENT)).resolves.toBeUndefined()
  })

  it('logs to console.error when the sink is unreachable [F-014]', async () => {
    fetchSpy.mockRejectedValue(new Error('ECONNREFUSED'))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { emit } = await import('../lib/audit/index.js')
    await emit(BASE_EVENT)
    expect(consoleSpy).toHaveBeenCalledOnce()
    consoleSpy.mockRestore()
  })

  // F-004: after switching to httpPost, fetch is still called internally but
  // the emit function must no longer call fetch directly.
  it('uses the shared HTTP client (httpPost) — not bare fetch', async () => {
    const { emit } = await import('../lib/audit/index.js')
    await emit(BASE_EVENT)
    // httpPost sets Content-Type; bare fetch() in the original impl also set it.
    // The distinguishing signal: httpPost wraps fetch with a timeout signal.
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(init.signal).toBeDefined()
  })
})

// F-003: JSON Schema conformance — every field in the JSON Schema's `required`
// array must be present in a well-formed AuditEvent, and nested required fields
// must also be satisfied.
describe('AuditEvent JSON Schema conformance', () => {
  const schemaPath = resolve(__dirname, '../../../schemas/audit-event.schema.json')
  const schema = JSON.parse(readFileSync(schemaPath, 'utf-8')) as {
    required: string[]
    properties: Record<string, { required?: string[] }>
  }

  it('BASE_EVENT satisfies all top-level required fields', () => {
    for (const field of schema.required) {
      expect(BASE_EVENT, `required field "${field}" is missing`).toHaveProperty(field)
    }
  })

  it('BASE_EVENT actor satisfies nested required fields', () => {
    const actorRequired = schema.properties['actor']?.required ?? []
    for (const field of actorRequired) {
      expect(BASE_EVENT.actor, `actor.${field} is missing`).toHaveProperty(field)
    }
  })

  it('BASE_EVENT subject satisfies nested required fields', () => {
    const subjectRequired = schema.properties['subject']?.required ?? []
    for (const field of subjectRequired) {
      expect(BASE_EVENT.subject, `subject.${field} is missing`).toHaveProperty(field)
    }
  })

  it('BASE_EVENT source satisfies nested required fields', () => {
    const sourceRequired = schema.properties['source']?.required ?? []
    for (const field of sourceRequired) {
      expect(BASE_EVENT.source, `source.${field} is missing`).toHaveProperty(field)
    }
  })

  it('BASE_EVENT metadata satisfies nested required fields', () => {
    const metaRequired = schema.properties['metadata']?.required ?? []
    for (const field of metaRequired) {
      expect(BASE_EVENT.metadata, `metadata.${field} is missing`).toHaveProperty(field)
    }
  })
})
