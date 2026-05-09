import { useEffect, useState } from 'react'
import { MagnifyingGlass, X } from '@phosphor-icons/react'
import { toggleQueryToken, clearFieldFromQuery } from '../../lib/auditQuery'

interface OutcomeChip {
  label: string
  token: string | null
}

const OUTCOME_CHIPS: OutcomeChip[] = [
  { label: 'All', token: null },
  { label: 'Success', token: 'outcome:success' },
  { label: 'Failure', token: 'outcome:failure' },
  { label: 'Denied', token: 'outcome:denied' },
]

const ACTION_CHIPS = [
  { label: 'authn.*', token: 'action:authn.*' },
  { label: 'deploy.*', token: 'action:deploy.*' },
  { label: 'read.*', token: 'action:read.*' },
  { label: 'config.*', token: 'action:config.*' },
  { label: 'schema.*', token: 'action:schema.*' },
]

const PLACEHOLDER_QUERIES = [
  'action:deploy.* outcome:failure',
  'actor:bhuff classification:cui',
  'outcome:denied',
  'action:authn.*',
  'svc-z-worker',
]

interface AuditSearchBarProps {
  query: string
  onChange: (q: string) => void
}

export function AuditSearchBar({ query, onChange }: AuditSearchBarProps) {
  const [placeholderIdx, setPlaceholderIdx] = useState(0)
  const [showPlaceholder, setShowPlaceholder] = useState(true)

  useEffect(() => {
    setShowPlaceholder(query.length === 0)
  }, [query])

  useEffect(() => {
    const id = setInterval(() => {
      setPlaceholderIdx((i) => (i + 1) % PLACEHOLDER_QUERIES.length)
    }, 3000)
    return () => clearInterval(id)
  }, [])

  const hasOutcomeFilter = OUTCOME_CHIPS.slice(1).some((c) => c.token !== null && query.includes(c.token))

  function handleOutcomeChip(chip: OutcomeChip) {
    if (chip.token === null) {
      onChange(clearFieldFromQuery(query, 'outcome'))
    } else {
      onChange(toggleQueryToken(query, chip.token))
    }
  }

  function handleActionChip(token: string) {
    onChange(toggleQueryToken(query, token))
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Search input */}
      <div className="relative">
        <MagnifyingGlass
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none"
        />
        <input
          id="audit-search"
          aria-label="Search audit events"
          type="text"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          className={[
            'w-full bg-zinc-900 border border-zinc-700 rounded-xl pl-9 pr-9 py-2.5',
            'text-sm font-mono text-zinc-100 placeholder:text-transparent outline-none',
            'focus:border-accent focus:ring-1 focus:ring-accent/20',
            'transition-colors duration-150',
          ].join(' ')}
          spellCheck={false}
          autoComplete="off"
        />

        {/* Animated placeholder — only visible when input is empty */}
        {showPlaceholder && (
          <span
            className={[
              'absolute left-9 top-1/2 -translate-y-1/2 text-sm font-mono text-zinc-600',
              'pointer-events-none select-none transition-opacity duration-300',
            ].join(' ')}
          >
            {PLACEHOLDER_QUERIES[placeholderIdx]}
          </span>
        )}

        {/* Clear button */}
        {query && (
          <button
            onClick={() => onChange('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
            aria-label="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Filter chips */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Outcome chips */}
        <div className="flex items-center gap-1.5" role="group" aria-label="Filter by outcome">
          {OUTCOME_CHIPS.map((chip) => {
            const isAll = chip.token === null
            const active = isAll ? !hasOutcomeFilter : chip.token !== null && query.includes(chip.token)
            return (
              <button
                key={chip.label}
                onClick={() => handleOutcomeChip(chip)}
                className={[
                  'px-2.5 py-1 rounded-md text-xs font-mono border transition-colors duration-150',
                  'active:scale-[0.97]',
                  active
                    ? 'bg-accent/10 border-accent/30 text-accent'
                    : 'bg-transparent border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-400',
                ].join(' ')}
              >
                {chip.label}
              </button>
            )
          })}
        </div>

        <div className="w-px h-4 bg-zinc-800" aria-hidden />

        {/* Action class chips */}
        <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label="Filter by action class">
          {ACTION_CHIPS.map((chip) => {
            const active = query.includes(chip.token)
            return (
              <button
                key={chip.token}
                onClick={() => handleActionChip(chip.token)}
                className={[
                  'px-2.5 py-1 rounded-md text-xs font-mono border transition-colors duration-150',
                  'active:scale-[0.97]',
                  active
                    ? 'bg-accent/10 border-accent/30 text-accent'
                    : 'bg-transparent border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-400',
                ].join(' ')}
              >
                {chip.label}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
