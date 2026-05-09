import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import type { AuditEvent } from '../lib/audit'

// audit.emit reads import.meta.env.VITE_AUDIT_SINK_URL at call time (not module
// load time), so vi.stubEnv works without dynamic imports here.

function makeEvent(): AuditEvent {
  return {
    ts: '2026-05-04T14:32:01.123Z',
    event_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    action: 'authn.success',
    actor: { id: 'user-abc', type: 'user' },
    subject: { type: 'config', id: 'https://keycloak.test/realms/fusion' },
    outcome: 'success',
    source: { request_id: 'req-001' },
    classification: 'none',
    metadata: { schema_version: '1.0.0', product: 'fusion-core' },
  }
}

describe('audit.emit', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_AUDIT_SINK_URL', 'https://audit.test/events')
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('POSTs to the configured sink URL with JSON content-type', async () => {
    const { emit } = await import('../lib/audit')
    await emit(makeEvent())

    expect(global.fetch).toHaveBeenCalledOnce()
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ]
    expect(url).toBe('https://audit.test/events')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('serialises the event payload correctly', async () => {
    const { emit } = await import('../lib/audit')
    const event = makeEvent()
    await emit(event)

    const body = JSON.parse(
      (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    ) as AuditEvent
    expect(body.action).toBe('authn.success')
    expect(body.metadata.product).toBe('fusion-core')
    expect(body.metadata.schema_version).toBe('1.0.0')
    expect(body.outcome).toBe('success')
  })

  it('does not call fetch when VITE_AUDIT_SINK_URL is not configured', async () => {
    vi.stubEnv('VITE_AUDIT_SINK_URL', '')
    const { emit } = await import('../lib/audit')
    await emit(makeEvent())
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('does not throw when the sink returns an error status', async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 500 }))
    const { emit } = await import('../lib/audit')
    await expect(emit(makeEvent())).resolves.toBeUndefined()
  })

  it('does not throw when the network is unreachable', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))
    const { emit } = await import('../lib/audit')
    await expect(emit(makeEvent())).resolves.toBeUndefined()
  })
})
