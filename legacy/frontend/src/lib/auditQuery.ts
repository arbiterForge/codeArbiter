import type { AuditEvent } from '../types/audit'

interface ParsedQuery {
  fields: Record<string, string>
  freetext: string
}

function parseQuery(q: string): ParsedQuery {
  const fields: Record<string, string> = {}
  const freetextParts: string[] = []

  for (const token of q.trim().split(/\s+/).filter(Boolean)) {
    const colonIdx = token.indexOf(':')
    if (colonIdx > 0) {
      fields[token.slice(0, colonIdx).toLowerCase()] = token.slice(colonIdx + 1)
    } else {
      freetextParts.push(token)
    }
  }

  return { fields, freetext: freetextParts.join(' ') }
}

function matchesWildcard(value: string, pattern: string): boolean {
  if (pattern.endsWith('*')) {
    return value.startsWith(pattern.slice(0, -1))
  }
  return value.toLowerCase() === pattern.toLowerCase()
}

export function matchesEvent(event: AuditEvent, query: string): boolean {
  if (!query.trim()) return true

  const { fields, freetext } = parseQuery(query)

  for (const [field, pattern] of Object.entries(fields)) {
    switch (field) {
      case 'action':
        if (!matchesWildcard(event.action, pattern)) return false
        break
      case 'outcome':
        if (!matchesWildcard(event.outcome, pattern)) return false
        break
      case 'actor':
        if (!matchesWildcard(event.actor.id, pattern)) return false
        break
      case 'subject':
        if (
          !matchesWildcard(event.subject.id, pattern) &&
          !matchesWildcard(event.subject.type, pattern)
        )
          return false
        break
      case 'classification':
        if (!matchesWildcard(event.classification, pattern)) return false
        break
    }
  }

  if (freetext) {
    const haystack = [
      event.action,
      event.actor.id,
      event.subject.id,
      event.subject.name ?? '',
      event.outcome,
      event.reason ?? '',
    ]
      .join(' ')
      .toLowerCase()
    if (!haystack.includes(freetext.toLowerCase())) return false
  }

  return true
}

export function toggleQueryToken(query: string, token: string): string {
  if (query.includes(token)) {
    return query
      .replace(new RegExp(`\\s*${token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*`), ' ')
      .trim()
  }
  return query.trim() ? `${query.trim()} ${token}` : token
}

export function clearFieldFromQuery(query: string, field: string): string {
  return query
    .replace(new RegExp(`\\s*${field}:\\S+\\s*`, 'g'), ' ')
    .trim()
}
