'use client'

import { Warning } from '@phosphor-icons/react'

interface AuthBypassBannerProps {
  active: boolean
}

export function AuthBypassBanner({ active }: AuthBypassBannerProps) {
  if (!active) return null

  return (
    <div
      role="alert"
      className="flex items-center gap-2 bg-amber-400/10 border-b border-amber-400/30 px-4 py-2 text-xs text-amber-300 font-mono"
    >
      <Warning size={14} weight="fill" className="shrink-0 text-amber-400" />
      <span>
        <strong className="font-semibold">AUTH BYPASS ACTIVE</strong>
        {' — '}
        NOT FOR USE OUTSIDE DEV ENVIRONMENT. Set{' '}
        <code className="bg-amber-400/10 px-1 rounded">VITE_AUTH_BYPASS=false</code> before
        any non-local deployment.
      </span>
    </div>
  )
}
