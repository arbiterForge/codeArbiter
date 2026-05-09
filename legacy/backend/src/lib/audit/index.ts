import type { AuditEvent } from './types'
import { httpPost } from '../../common/http.js'
export type { AuditEvent }

// SHORTCUT [S1]: fire-and-forget HTTP POST; fail-open on network errors.
// Payback trigger: Stage 3 promotion — replace with NATS JetStream and enforce
// fail-closed per AU-5 (audit emit failure must abort the originating request).
export async function emit(event: AuditEvent): Promise<void> {
  const sinkUrl = process.env.AUDIT_SINK_URL
  if (!sinkUrl) return

  // eslint-disable-next-line no-console
  await httpPost(sinkUrl, event).catch((err: unknown) => { console.error('[audit] emit failed — sink unreachable:', err) })
}
