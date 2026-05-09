import { render, screen } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useAuth } from '../lib/auth/useAuth'
import { AuthContext } from '../lib/auth/AuthProvider'
import type { AuthContextValue } from '../lib/auth/types'

// ── helpers ──────────────────────────────────────────────────────────────────

function ThrowingConsumer() {
  useAuth()
  return null
}

function SafeConsumer() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="authenticated">{String(auth.isAuthenticated)}</span>
      <span data-testid="bypass">{String(auth.isBypass)}</span>
      <span data-testid="user">{auth.user ? auth.user.sub : 'null'}</span>
    </div>
  )
}

const STUB_CTX: AuthContextValue = {
  user: { sub: 'u-1', email: 'u@test.com', name: 'Test', groups: [] },
  isAuthenticated: true,
  isLoading: false,
  isBypass: false,
  signIn: vi.fn(),
  signOut: vi.fn(),
}

const NULL_USER_CTX: AuthContextValue = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  isBypass: false,
  signIn: vi.fn(),
  signOut: vi.fn(),
}

// ── tests ────────────────────────────────────────────────────────────────────

describe('useAuth', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_AUTH_BYPASS', 'false')
    vi.stubEnv('VITE_OIDC_ISSUER', 'https://keycloak.test/realms/fusion')
    vi.stubEnv('VITE_OIDC_CLIENT_ID', 'fusion-ui')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('throws when called outside an AuthProvider', () => {
    // Suppress React's expected error boundary output in the test runner
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    expect(() => render(<ThrowingConsumer />)).toThrow(
      'useAuth must be used inside AuthProvider',
    )
    consoleSpy.mockRestore()
  })

  it('returns the context value when inside an AuthProvider', () => {
    render(
      <AuthContext.Provider value={STUB_CTX}>
        <SafeConsumer />
      </AuthContext.Provider>,
    )
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user').textContent).toBe('u-1')
    expect(screen.getByTestId('bypass').textContent).toBe('false')
  })

  it('reflects isAuthenticated=false when user is null', () => {
    render(
      <AuthContext.Provider value={NULL_USER_CTX}>
        <SafeConsumer />
      </AuthContext.Provider>,
    )
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('user').textContent).toBe('null')
  })
})
