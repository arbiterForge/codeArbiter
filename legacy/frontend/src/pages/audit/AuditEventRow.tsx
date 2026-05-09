import { memo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CaretRight } from '@phosphor-icons/react'
import type { AuditEvent, AuditOutcome } from '../../types/audit'

const OUTCOME_STYLE: Record<AuditOutcome, string> = {
  success: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
  failure: 'text-rose-400 bg-rose-400/10 border-rose-400/20',
  denied: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
}

const CLASSIFICATION_STYLE: Record<string, string> = {
  none: 'text-zinc-600 border-zinc-800',
  cui: 'text-amber-400/80 border-amber-400/20 bg-amber-400/5',
  secret_ref: 'text-rose-400/80 border-rose-400/20 bg-rose-400/5',
}

function getActionStyle(action: string): string {
  if (action.startsWith('authn.')) return 'text-sky-400 bg-sky-400/10 border-sky-400/20'
  if (action.startsWith('authz.')) return 'text-amber-400 bg-amber-400/10 border-amber-400/20'
  if (action.startsWith('deploy.') || action.startsWith('teardown.'))
    return 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20'
  if (action.startsWith('read.')) return 'text-rose-400 bg-rose-400/10 border-rose-400/20'
  if (action.startsWith('role.') || action.startsWith('config.') || action.startsWith('key.'))
    return 'text-orange-400 bg-orange-400/10 border-orange-400/20'
  return 'text-zinc-400 bg-zinc-800 border-zinc-700'
}

function formatTs(ts: string): string {
  return ts.replace('T', ' ').slice(0, 23)
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3 min-w-0">
      <span className="text-zinc-600 shrink-0 w-44 truncate font-mono text-[11px]">{label}</span>
      <span className="text-zinc-300 font-mono text-[11px] break-all">{value}</span>
    </div>
  )
}

interface AuditEventRowProps {
  event: AuditEvent
}

export const AuditEventRow = memo(function AuditEventRow({ event }: AuditEventRowProps) {
  const [expanded, setExpanded] = useState(false)

  const detailFields: [string, string][] = [
    ['event_id', event.event_id],
    ['ts', formatTs(event.ts) + ' UTC'],
    ['source.request_id', event.source.request_id],
    ...(event.source.ip ? [['source.ip', event.source.ip] as [string, string]] : []),
    ...(event.source.user_agent
      ? [['source.user_agent', event.source.user_agent] as [string, string]]
      : []),
    ...(event.actor.session_id
      ? [['actor.session_id', event.actor.session_id] as [string, string]]
      : []),
    ['actor.type', event.actor.type],
    ['subject.type', event.subject.type],
    ...(event.subject.name ? [['subject.name', event.subject.name] as [string, string]] : []),
    ...(event.git_sha ? [['git_sha', event.git_sha] as [string, string]] : []),
    ...(event.reason ? [['reason', event.reason] as [string, string]] : []),
    ['metadata.schema_version', event.metadata.schema_version],
    ['metadata.product', event.metadata.product],
    ...(event.environment ? [['environment', event.environment] as [string, string]] : []),
  ]

  return (
    <div className="border-b border-zinc-800/60 last:border-0">
      {/* Row */}
      <div
        data-testid="audit-event-row"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className={[
          'grid items-center gap-4 px-4 py-3 cursor-pointer select-none',
          'transition-colors duration-100',
          expanded ? 'bg-zinc-900/60' : 'hover:bg-zinc-900/40',
        ].join(' ')}
        style={{ gridTemplateColumns: '188px 1fr auto auto auto auto 20px' }}
      >
        {/* Timestamp */}
        <span className="font-mono text-[11px] text-zinc-500 shrink-0 tabular-nums">
          {formatTs(event.ts)}
        </span>

        {/* Action badge */}
        <span
          className={[
            'inline-flex items-center px-2 py-0.5 rounded border font-mono text-[10px] uppercase tracking-wide w-fit',
            getActionStyle(event.action),
          ].join(' ')}
        >
          {event.action}
        </span>

        {/* Outcome chip */}
        <span
          className={[
            'inline-flex items-center px-2 py-0.5 rounded-full border font-mono text-[10px]',
            OUTCOME_STYLE[event.outcome],
          ].join(' ')}
        >
          {event.outcome}
        </span>

        {/* Actor */}
        <span className="text-xs font-mono text-zinc-400 shrink-0">{event.actor.id}</span>

        {/* Subject */}
        <span className="text-xs font-mono text-zinc-500 shrink-0">
          {event.subject.type}:{event.subject.id}
        </span>

        {/* Classification */}
        <span
          className={[
            'inline-flex items-center px-1.5 py-0.5 rounded border font-mono text-[10px] uppercase',
            CLASSIFICATION_STYLE[event.classification] ?? CLASSIFICATION_STYLE.none,
          ].join(' ')}
        >
          {event.classification}
        </span>

        {/* Expand chevron */}
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          className="text-zinc-600 flex items-center justify-center"
        >
          <CaretRight size={12} weight="bold" />
        </motion.span>
      </div>

      {/* Expandable detail */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            data-testid="audit-event-detail"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ type: 'spring', stiffness: 350, damping: 32 }}
            style={{ overflow: 'hidden' }}
          >
            <div
              className={[
                'mx-4 mb-3 px-4 py-3 rounded-lg bg-zinc-950',
                'border-l-2 border-l-accent/40 border border-zinc-800',
                'flex flex-col gap-1.5',
              ].join(' ')}
            >
              {detailFields.map(([label, value]) => (
                <DetailRow key={label} label={label} value={value} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
})
