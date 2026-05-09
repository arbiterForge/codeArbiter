import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react'
import { UserManager, WebStorageStateStore, InMemoryWebStorage } from 'oidc-client-ts'
import type { AuthContextValue, FusionUser } from './types'

export const AuthContext = createContext<AuthContextValue | null>(null)

const BYPASS_USER: FusionUser = {
  sub: 'dev-bypass',
  email: 'dev@localhost',
  name: 'Dev Bypass',
  groups: ['fusion-admins'],
}

const isBypass = import.meta.env.VITE_AUTH_BYPASS === 'true'

// Tokens stored in memory only — never localStorage (defense posture).
export const userManager = isBypass
  ? null
  : new UserManager({
      authority: import.meta.env.VITE_OIDC_ISSUER,
      client_id: import.meta.env.VITE_OIDC_CLIENT_ID,
      redirect_uri: `${window.location.origin}/auth/callback`,
      response_type: 'code',
      scope: 'openid profile email groups',
      userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<FusionUser | null>(isBypass ? BYPASS_USER : null)
  const [isLoading, setIsLoading] = useState(!isBypass)

  useEffect(() => {
    if (isBypass || !userManager) return

    userManager.getUser().then((oidcUser) => {
      if (oidcUser && !oidcUser.expired) {
        setUser({
          sub: oidcUser.profile.sub,
          email: oidcUser.profile.email ?? '',
          name: oidcUser.profile.name ?? '',
          groups: (oidcUser.profile['groups'] as string[]) ?? [],
        })
      }
      setIsLoading(false)
    })

    const onLoaded = userManager.events.addUserLoaded((oidcUser) => {
      setUser({
        sub: oidcUser.profile.sub,
        email: oidcUser.profile.email ?? '',
        name: oidcUser.profile.name ?? '',
        groups: (oidcUser.profile['groups'] as string[]) ?? [],
      })
    })

    const onUnloaded = userManager.events.addUserUnloaded(() => setUser(null))

    return () => {
      onLoaded()
      onUnloaded()
    }
  }, [])

  const signIn = useCallback(async () => {
    if (!userManager) return
    await userManager.signinRedirect()
  }, [])

  const signOut = useCallback(async () => {
    if (!userManager) return
    await userManager.signoutRedirect()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        isBypass,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
