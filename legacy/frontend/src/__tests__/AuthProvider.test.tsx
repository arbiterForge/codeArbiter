import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useContext } from 'react'

// ── oidc-client-ts mock ──────────────────────────────────────────────────────
// vi.hoisted() ensures these are available inside the vi.mock() factory.

const mockGetUser = vi.hoisted(() => vi.fn())
const mockSigninRedirect = vi.hoisted(() => vi.fn())
const mockSignoutRedirect = vi.hoisted(() => vi.fn())
const mockAddUserLoaded = vi.hoisted(() => vi.fn())
const mockAddUserUnloaded = vi.hoisted(() => vi.fn())

vi.mock('oidc-client-ts', () => {
  class FakeUserManager {
    events = {
      addUserLoaded: mockAddUserLoaded,
      addUserUnloaded: mockAddUserUnloaded,
    }
    getUser = mockGetUser
    signinRedirect = mockSigninRedirect
    signoutRedirect = mockSignoutRedirect
  }
  return {
    UserManager: FakeUserManager,
    InMemoryWebStorage: Object,
    // eslint-disable-next-line @typescript-eslint/no-extraneous-class
    WebStorageStateStore: class WebStorageStateStore {
      constructor(_opts: unknown) { void _opts }
    },
  }
})

// ── renderProvider ────────────────────────────────────────────────────────────
// Dynamic import is required because AuthProvider evaluates `isBypass` and
// `userManager` at module load time from import.meta.env. vi.resetModules()
// + dynamic import gives each test a fresh module evaluation.
//
// The Consumer is defined INSIDE this function so it closes over the same
// AuthContext instance that was just imported — avoiding the "two context
// instances" problem that occurs when the static import and dynamic import
// produce different module objects.

async function renderProvider() {
  const { AuthProvider, AuthContext } = await import('../lib/auth/AuthProvider')

  function Consumer() {
    const ctx = useContext(AuthContext)
    if (!ctx) return <span data-testid="no-ctx">no ctx</span>
    return (
      <div>
        <span data-testid="loading">{String(ctx.isLoading)}</span>
        <span data-testid="authenticated">{String(ctx.isAuthenticated)}</span>
        <span data-testid="bypass">{String(ctx.isBypass)}</span>
        <span data-testid="user">{ctx.user ? ctx.user.sub : 'null'}</span>
        <button onClick={ctx.signIn}>sign-in</button>
        <button onClick={ctx.signOut}>sign-out</button>
      </div>
    )
  }

  return render(
    <AuthProvider>
      <Consumer />
    </AuthProvider>,
  )
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe('AuthProvider (non-bypass)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('VITE_AUTH_BYPASS', 'false')
    vi.stubEnv('VITE_OIDC_ISSUER', 'https://keycloak.test/realms/fusion')
    vi.stubEnv('VITE_OIDC_CLIENT_ID', 'fusion-ui')
    mockGetUser.mockResolvedValue(null)
    mockAddUserLoaded.mockReturnValue(vi.fn())
    mockAddUserUnloaded.mockReturnValue(vi.fn())
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('starts loading, then resolves to unauthenticated when no stored session', async () => {
    await renderProvider()
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('user').textContent).toBe('null')
  })

  it('hydrates from a valid stored OIDC session', async () => {
    mockGetUser.mockResolvedValue({
      expired: false,
      profile: { sub: 'user-abc', email: 'user@test.com', name: 'Test User', groups: ['fusion-ops'] },
    })

    await renderProvider()
    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('true'))
    expect(screen.getByTestId('user').textContent).toBe('user-abc')
  })

  it('treats an expired stored session as unauthenticated', async () => {
    mockGetUser.mockResolvedValue({
      expired: true,
      profile: { sub: 'user-xyz', email: '', name: '', groups: [] },
    })

    await renderProvider()
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
  })

  it('calls signinRedirect when signIn() is invoked', async () => {
    mockSigninRedirect.mockResolvedValue(undefined)
    await renderProvider()
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await act(async () => {
      await userEvent.click(screen.getByText('sign-in'))
    })

    expect(mockSigninRedirect).toHaveBeenCalledOnce()
  })

  it('calls signoutRedirect and clears user when signOut() is invoked', async () => {
    mockGetUser.mockResolvedValue({
      expired: false,
      profile: { sub: 'user-abc', email: '', name: '', groups: [] },
    })
    mockSignoutRedirect.mockResolvedValue(undefined)

    await renderProvider()
    await waitFor(() => expect(screen.getByTestId('authenticated').textContent).toBe('true'))

    await act(async () => {
      await userEvent.click(screen.getByText('sign-out'))
    })

    expect(mockSignoutRedirect).toHaveBeenCalledOnce()
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
  })

  it('registers and cleans up addUserLoaded / addUserUnloaded listeners', async () => {
    const cleanupLoaded = vi.fn()
    const cleanupUnloaded = vi.fn()
    mockAddUserLoaded.mockReturnValue(cleanupLoaded)
    mockAddUserUnloaded.mockReturnValue(cleanupUnloaded)

    const { unmount } = await renderProvider()
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    unmount()

    expect(cleanupLoaded).toHaveBeenCalledOnce()
    expect(cleanupUnloaded).toHaveBeenCalledOnce()
  })
})

describe('AuthProvider (bypass mode)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('VITE_AUTH_BYPASS', 'true')
    mockAddUserLoaded.mockReturnValue(vi.fn())
    mockAddUserUnloaded.mockReturnValue(vi.fn())
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('immediately authenticates as dev-bypass without calling getUser', async () => {
    await renderProvider()
    expect(screen.getByTestId('loading').textContent).toBe('false')
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user').textContent).toBe('dev-bypass')
    expect(screen.getByTestId('bypass').textContent).toBe('true')
    expect(mockGetUser).not.toHaveBeenCalled()
  })
})
