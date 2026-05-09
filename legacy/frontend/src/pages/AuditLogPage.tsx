import { useMemo, useState } from 'react'
import { ShieldCheck } from '@phosphor-icons/react'
import { matchesEvent } from '../lib/auditQuery'
import { AuditSearchBar } from './audit/AuditSearchBar'
import { AuditEventRow } from './audit/AuditEventRow'
import type { AuditEvent } from '../types/audit'

interface AuditLogPageProps {
  events: AuditEvent[]
}

export function AuditLogPage({ events }: AuditLogPageProps) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(
    () => events.filter((e) => matchesEvent(e, query)),
    [events, query],
  )

  return (
    <div className="flex flex-col gap-6 px-8 py-8 w-full min-h-0">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} weight="fill" className="text-accent" />
            <p className="text-xs font-mono text-zinc-600 uppercase tracking-widest">
              Z-AUDIT · append-only
            </p>
          </div>
          <h1 className="text-xl font-semibold text-zinc-100">Audit Log</h1>
        </div>

        <div className="flex flex-col items-end gap-0.5">
          <span
            data-testid="event-count"
            className="text-2xl font-mono font-semibold text-zinc-100 tabular-nums"
          >
            {filtered.length}
          </span>
          <span className="text-xs text-zinc-600 font-mono">
            {filtered.length === events.length
              ? 'events'
              : `of ${events.length} events`}
          </span>
        </div>
      </div>

      {/* Search & filter */}
      <AuditSearchBar query={query} onChange={setQuery} />

      {/* Event list */}
      <div className="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950">
        {/* Column headers */}
        <div
          className="grid items-center gap-4 px-4 py-2 border-b border-zinc-800 bg-zinc-900"
          style={{ gridTemplateColumns: '188px 1fr auto auto auto auto 20px' }}
        >
          {['Timestamp', 'Action', 'Outcome', 'Actor', 'Subject', 'Class', ''].map((h) => (
            <span key={h} className="text-[10px] font-mono uppercase tracking-widest text-zinc-600">
              {h}
            </span>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div
            data-testid="audit-empty"
            className="flex flex-col items-center justify-center gap-3 py-16 px-8"
          >
            <ShieldCheck size={32} className="text-zinc-800" />
            <div className="flex flex-col items-center gap-1">
              <p className="text-sm font-medium text-zinc-500">No events match</p>
              <p className="text-xs text-zinc-700 font-mono">
                {query ? `query: ${query}` : 'no events in this sink'}
              </p>
            </div>
          </div>
        ) : (
          <div>
            {filtered.map((event) => (
              <AuditEventRow key={event.event_id} event={event} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
