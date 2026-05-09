import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { AuthCallbackPage } from '../pages/AuthCallbackPage'

// vi.hoisted() ensures these are available when vi.mock() factories run —
// vi.mock() calls are hoisted to the top of the file by Vitest's transform.
const mockNavigate = vi.hoisted(() => vi.fn())
const mockSigninRedirectCallback = vi.hoisted(() => vi.fn())
const mockAuditEmit = vi.hoisted(() => vi.fn())

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../lib/auth/AuthProvider', () => ({
  userManager: { signinRedirectCallback: mockSigninRedirectCallback },
}))

vi.mock('../lib/audit', () => ({
  emit: mockAuditEmit,
}))

describe('AuthCallbackPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuditEmit.mockResolvedValue(undefined)
  })

  it('shows a loading state while the callback is in flight', () => {
    mockSigninRedirectCallback.mockReturnValue(new Promise<void>(() => undefined))
    render(<AuthCallbackPage />)
    expect(screen.getByText(/completing sign-in/i)).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('calls signinRedirectCallback and navigates to / on success', async () => {
    mockSigninRedirectCallback.mockResolvedValue({ profile: { sub: 'user-abc' } })
    render(<AuthCallbackPage />)
    await waitFor(() => expect(mockSigninRedirectCallback).toHaveBeenCalledOnce())
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true }))
  })

  it('emits authn.success with the actor sub on successful callback', async () => {
    mockSigninRedirectCallback.mockResolvedValue({ profile: { sub: 'user-abc' } })
    render(<AuthCallbackPage />)
    await waitFor(() => expect(mockAuditEmit).toHaveBeenCalledOnce())
    const event = mockAuditEmit.mock.calls[0][0]
    expect(event.action).toBe('authn.success')
    expect(event.outcome).toBe('success')
    expect(event.actor.id).toBe('user-abc')
    expect(event.actor.type).toBe('user')
    expect(event.metadata.product).toBe('fusion-core')
  })

  it('shows an error alert when signinRedirectCallback rejects', async () => {
    mockSigninRedirectCallback.mockRejectedValue(new Error('Token expired'))
    render(<AuthCallbackPage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/Token expired/)).toBeInTheDocument()
  })

  it('emits authn.failure with the error reason on callback rejection', async () => {
    mockSigninRedirectCallback.mockRejectedValue(new Error('Token expired'))
    render(<AuthCallbackPage />)
    await waitFor(() => expect(mockAuditEmit).toHaveBeenCalledOnce())
    const event = mockAuditEmit.mock.calls[0][0]
    expect(event.action).toBe('authn.failure')
    expect(event.outcome).toBe('failure')
    expect(event.reason).toBe('Token expired')
    expect(event.actor.id).toBe('unknown')
  })

  it('does not navigate on error', async () => {
    mockSigninRedirectCallback.mockRejectedValue(new Error('bad state'))
    render(<AuthCallbackPage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})
