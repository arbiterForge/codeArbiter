import { render, screen, within } from '@testing-library/react'
import { vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { DeployWizardPage } from '../pages/DeployWizardPage'
import type { SolutionDetail } from '../types/solution'

vi.mock('../lib/auth/useAuth', () => ({
  useAuth: () => ({
    user: { sub: 'test-user', email: 'test@test.com', name: 'Test', groups: [] },
    isAuthenticated: true,
    isLoading: false,
    isBypass: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}))

const mockSolution: SolutionDetail = {
  id: 'sol-001',
  name: 'Identity Bridge',
  version: '1.2.0',
  maturity: 'mvp',
  description: 'AD-to-Keycloak federation adapter',
  graph: {
    nodes: [
      {
        id: 'node-1',
        nodeType: 'keycloak',
        label: 'Keycloak IdP',
        criticality: 'critical_path',
        status: 'healthy',
        version: '24.0.1',
      },
    ],
    adapters: [],
  },
}

const renderWizard = (search = '') =>
  render(
    <MemoryRouter initialEntries={[`/solutions/sol-001/deploy${search}`]}>
      <Routes>
        <Route
          path="/solutions/:id/deploy"
          element={<DeployWizardPage solution={mockSolution} />}
        />
      </Routes>
    </MemoryRouter>,
  )

describe('DeployWizardPage', () => {
  describe('step routing', () => {
    it('renders step 1 by default', () => {
      renderWizard()
      expect(screen.getByTestId('step-1')).toBeInTheDocument()
    })

    it('renders step 2 when ?step=2 is in the URL', () => {
      renderWizard('?step=2')
      expect(screen.getByTestId('step-2')).toBeInTheDocument()
    })

    it('redirects to step 1 when step > 1 and form is empty', () => {
      renderWizard('?step=3')
      expect(screen.getByTestId('step-1')).toBeInTheDocument()
    })

    it('clamps out-of-range step values to step 1', () => {
      renderWizard('?step=99')
      expect(screen.getByTestId('step-1')).toBeInTheDocument()
    })
  })

  describe('step indicator', () => {
    it('shows all four step labels', () => {
      renderWizard()
      const nav = screen.getByRole('navigation', { name: /deployment steps/i })
      expect(within(nav).getByText('Configure')).toBeInTheDocument()
      expect(within(nav).getByText('Compliance')).toBeInTheDocument()
      expect(within(nav).getByText('Confirm')).toBeInTheDocument()
      expect(within(nav).getByText('Monitor')).toBeInTheDocument()
    })
  })

  describe('navigation', () => {
    it('next button is disabled when required fields are empty', () => {
      renderWizard()
      expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
    })

    it('back button is not visible on step 1', () => {
      renderWizard()
      expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument()
    })

    it('back button is visible on step 2', () => {
      renderWizard('?step=2')
      expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument()
    })

    it('shows the solution name in the wizard header', () => {
      renderWizard()
      expect(screen.getByText('Identity Bridge')).toBeInTheDocument()
    })
  })
})
