import { describe, it, expect } from 'vitest'
import { toggleQueryToken, clearFieldFromQuery } from '../lib/auditQuery'

// ─── toggleQueryToken ────────────────────────────────────────────────────────
//
// Contract: if the token is already present, remove it and normalise whitespace.
// If absent, append it (with a space separator if the query is non-empty).

describe('toggleQueryToken', () => {
  describe('adding a token', () => {
    it('returns the token alone when the query is empty', () => {
      expect(toggleQueryToken('', 'outcome:success')).toBe('outcome:success')
    })

    it('appends the token with a space when the query is non-empty', () => {
      expect(toggleQueryToken('action:authn.success', 'outcome:success')).toBe(
        'action:authn.success outcome:success',
      )
    })

    it('trims leading/trailing whitespace from the existing query before appending', () => {
      expect(toggleQueryToken('  action:deploy  ', 'outcome:failure')).toBe(
        'action:deploy outcome:failure',
      )
    })
  })

  describe('removing a token', () => {
    it('removes the token when it is the only term', () => {
      expect(toggleQueryToken('outcome:success', 'outcome:success')).toBe('')
    })

    it('removes the token from the middle and collapses extra whitespace', () => {
      expect(toggleQueryToken('action:deploy outcome:success actor:user-1', 'outcome:success')).toBe(
        'action:deploy actor:user-1',
      )
    })

    it('removes the token from the start', () => {
      expect(toggleQueryToken('outcome:success action:deploy', 'outcome:success')).toBe(
        'action:deploy',
      )
    })

    it('removes the token from the end', () => {
      expect(toggleQueryToken('action:deploy outcome:success', 'outcome:success')).toBe(
        'action:deploy',
      )
    })
  })

  // The token is first run through a regex special-character escape pass before
  // being inserted into the RegExp pattern. Without this, a token like
  // `action:authn.*` would compile to /.../action:authn.*.../ where `.*` means
  // "any character, zero or more times" — greedily consuming unrelated tokens.
  //
  // The escape replaces each metacharacter (. * + ? ^ $ { } ( ) | [ ] \) with
  // `\` + the character, turning `action:authn.*` into `action:authn\.\*` in
  // the pattern so it matches the literal string only.
  describe('regex special-character escaping', () => {
    it('correctly removes a token containing a dot (field:value.subvalue)', () => {
      const q = 'action:authn.success outcome:failure'
      expect(toggleQueryToken(q, 'action:authn.success')).toBe('outcome:failure')
    })

    it('correctly removes a token containing a wildcard asterisk', () => {
      const q = 'action:deploy.* outcome:success'
      expect(toggleQueryToken(q, 'action:deploy.*')).toBe('outcome:success')
    })

    it('correctly adds a dot-containing token that is absent', () => {
      expect(toggleQueryToken('outcome:failure', 'action:authn.success')).toBe(
        'outcome:failure action:authn.success',
      )
    })

    it('does not treat an adjacent token as matching due to unescaped dot', () => {
      // Without escaping: removing `action:authnXsuccess` would accidentally match
      // `action:authn.success` because `.` means "any character". With escaping it
      // does not match and the query is returned unchanged.
      const q = 'action:authn.success outcome:success'
      // The token `action:authnXsuccess` is not present, so toggles it ON.
      const result = toggleQueryToken(q, 'action:authnXsuccess')
      expect(result).toBe('action:authn.success outcome:success action:authnXsuccess')
    })
  })
})

// ─── clearFieldFromQuery ─────────────────────────────────────────────────────
//
// Contract: remove ALL `field:value` tokens for the given field name, regardless
// of value. The regex is `\s*field:\S+\s*` (global) — `\S+` matches any run of
// non-whitespace characters after the colon.

describe('clearFieldFromQuery', () => {
  it('removes a single field:value token and trims the result', () => {
    expect(clearFieldFromQuery('action:deploy outcome:success', 'action')).toBe('outcome:success')
  })

  it('removes all occurrences of the same field (global flag)', () => {
    // The regex uses /g so every `outcome:X` token is removed, not just the first.
    const q = 'outcome:success action:deploy outcome:failure'
    expect(clearFieldFromQuery(q, 'outcome')).toBe('action:deploy')
  })

  it('leaves unrelated tokens intact', () => {
    expect(clearFieldFromQuery('actor:user-1 action:deploy', 'outcome')).toBe(
      'actor:user-1 action:deploy',
    )
  })

  it('returns an empty string when the only token matches the field', () => {
    expect(clearFieldFromQuery('action:deploy', 'action')).toBe('')
  })

  it('returns an empty string when the query is already empty', () => {
    expect(clearFieldFromQuery('', 'action')).toBe('')
  })

  it('handles a field at the start of the query without leaving a leading space', () => {
    const result = clearFieldFromQuery('action:deploy outcome:success', 'action')
    expect(result).toBe('outcome:success')
    expect(result.startsWith(' ')).toBe(false)
  })

  it('handles a field at the end without leaving a trailing space', () => {
    const result = clearFieldFromQuery('outcome:success action:deploy', 'action')
    expect(result).toBe('outcome:success')
    expect(result.endsWith(' ')).toBe(false)
  })

  it('matches multi-character values including dots and slashes', () => {
    // \S+ matches any non-whitespace run, so `actor:https://id.internal/user`
    // is removed as a single token.
    const q = 'actor:https://id.internal/user action:deploy'
    expect(clearFieldFromQuery(q, 'actor')).toBe('action:deploy')
  })
})
