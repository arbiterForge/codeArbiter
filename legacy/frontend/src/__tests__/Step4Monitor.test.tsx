import { render, screen, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { Step4Monitor } from '../pages/deploy/Step4Monitor'
import type { SolutionDetail } from '../types/solution'

const mockAuditEmit = vi.hoisted(() => vi.fn())

vi.mock('../lib/audit', () => ({
  emit: mockAuditEmit,
}))

const mockSolution: SolutionDetail = {
  id: 'sol-001',
  name: 'Identity Bridge',
  version: '1.2.0',
  maturity: 'mvp',
  description: 'AD-to-Keycloak federation adapter',
  graph: { nodes: [], adapters: [] },
}

describe('Step4Monitor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuditEmit.mockResolvedValue(undefined)
  })

  it('shows the queued status on initial render', () => {
    render(<Step4Monitor solution={mockSolution} actorSub="user-abc" />)
    expect(screen.getByTestId('deploy-status')).toHaveTextContent(/queued/i)
  })

  it('renders the log output container', () => {
    render(<Step4Monitor solution={mockSolution} actorSub="user-abc" />)
    expect(screen.getByTestId('deploy-log')).toBeInTheDocument()
  })

  it('shows the solution name in the monitor header', () => {
    render(<Step4Monitor solution={mockSolution} actorSub="user-abc" />)
    expect(screen.getByText('Identity Bridge')).toBeInTheDocument()
  })

  describe('audit events', () => {
    beforeEach(() => {
      // Only fake setTimeout/clearTimeout — leave requestAnimationFrame real so
      // Framer Motion's animation loop doesn't create an infinite timer chain.
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('emits deploy.solution with outcome success when the deployment succeeds', async () => {
      render(<Step4Monitor solution={mockSolution} actorSub="user-abc" />)

      // Total simulated duration: 900 + 2200 + 2600 + 1600 = 7300ms
      await act(async () => {
        await vi.advanceTimersByTimeAsync(8000)
      })

      expect(mockAuditEmit).toHaveBeenCalledOnce()
      const event = mockAuditEmit.mock.calls[0][0]
      expect(event.action).toBe('deploy.solution')
      expect(event.outcome).toBe('success')
      expect(event.actor.id).toBe('user-abc')
      expect(event.actor.type).toBe('user')
      expect(event.subject.type).toBe('solution')
      expect(event.subject.id).toBe('sol-001')
      expect(event.subject.name).toBe('Identity Bridge')
      expect(event.metadata.product).toBe('fusion-core')
      expect(event.class_uid).toBe(6001)
    })

    it('does not emit the audit event on initial render (only on terminal state)', async () => {
      render(<Step4Monitor solution={mockSolution} actorSub="user-abc" />)
      // No timers advanced — still in queued state
      expect(mockAuditEmit).not.toHaveBeenCalled()
    })

    it('emits deploy.solution with outcome failure and reason when deployment fails', async () => {
      const failureStages = [
        {
          status: 'failed' as const,
          duration: 0,
          logs: [{ ts: '2026-01-01 00:00:00.000', level: 'error' as const, msg: 'TASK FAILED' }],
        },
      ]
      render(<Step4Monitor solution={mockSolution} actorSub="user-abc" stages={failureStages} />)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      expect(mockAuditEmit).toHaveBeenCalledOnce()
      const event = mockAuditEmit.mock.calls[0][0]
      expect(event.action).toBe('deploy.solution')
      expect(event.outcome).toBe('failure')
      expect(event.reason).toBeDefined()
      expect(event.actor.id).toBe('user-abc')
      expect(event.subject.id).toBe('sol-001')
    })

    it('shows the Failed status badge when deployment fails', async () => {
      const failureStages = [
        {
          status: 'failed' as const,
          duration: 0,
          logs: [],
        },
      ]
      render(<Step4Monitor solution={mockSolution} actorSub="user-abc" stages={failureStages} />)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      expect(screen.getByTestId('deploy-status')).toHaveTextContent(/failed/i)
    })
  })
})
