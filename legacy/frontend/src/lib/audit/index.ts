import type { AuditEvent } from './types'
export type { AuditEvent }

// SHORTCUT [S1]: fire-and-forget HTTP POST; fail-open on network errors.
// Payback trigger: Stage 3 promotion — replace with NATS JetStream and enforce
// fail-closed per AU-5 (audit emit failure must abort the originating request).
export async function emit(event: AuditEvent): Promise<void> {
  const sinkUrl = import.meta.env.VITE_AUDIT_SINK_URL
  if (!sinkUrl) return

  await fetch(sinkUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(event),
  }).catch(() => undefined)
}
