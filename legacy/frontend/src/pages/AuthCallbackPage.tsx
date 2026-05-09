import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { userManager } from '../lib/auth/AuthProvider'
import { emit } from '../lib/audit'

export function AuthCallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!userManager) {
      navigate('/', { replace: true })
      return
    }

    userManager
      .signinRedirectCallback()
      .then((user) => {
        void emit({
          ts: new Date().toISOString(),
          event_id: crypto.randomUUID(),
          action: 'authn.success',
          actor: { id: user.profile.sub, type: 'user' },
          subject: { type: 'config', id: import.meta.env.VITE_OIDC_ISSUER ?? 'oidc' },
          outcome: 'success',
          source: { request_id: crypto.randomUUID() },
          classification: 'none',
          metadata: { schema_version: '1.0.0', product: 'fusion-core' },
          class_uid: 3001,
          severity_id: 1,
        })
        navigate('/', { replace: true })
      })
      .catch((err: unknown) => {
        const reason = err instanceof Error ? err.message : 'Authentication failed'
        void emit({
          ts: new Date().toISOString(),
          event_id: crypto.randomUUID(),
          action: 'authn.failure',
          actor: { id: 'unknown', type: 'user' },
          subject: { type: 'config', id: import.meta.env.VITE_OIDC_ISSUER ?? 'oidc' },
          outcome: 'failure',
          reason,
          source: { request_id: crypto.randomUUID() },
          classification: 'none',
          metadata: { schema_version: '1.0.0', product: 'fusion-core' },
          class_uid: 3001,
          severity_id: 3,
        })
        setError(reason)
      })
  }, [navigate])

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div role="alert" className="max-w-md space-y-3 px-6 text-center">
          <p className="font-mono text-sm text-red-400">Sign-in failed</p>
          <p className="font-mono text-xs text-zinc-500">{error}</p>
          <a href="/" className="block font-mono text-xs text-zinc-400 underline underline-offset-4">
            Return to home
          </a>
        </div>
      </div>
    )
  }

  return (
    <div
      role="status"
      aria-label="Completing sign-in"
      className="flex min-h-screen items-center justify-center bg-zinc-950"
    >
      <p className="font-mono text-sm text-zinc-500">Completing sign-in…</p>
    </div>
  )
}
