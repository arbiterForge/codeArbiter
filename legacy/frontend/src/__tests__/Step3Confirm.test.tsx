import { render, screen, within } from '@testing-library/react'
import { Step3Confirm } from '../pages/deploy/Step3Confirm'
import type { DeployFormData } from '../pages/DeployWizardPage'
import type { SolutionDetail } from '../types/solution'

const mockSolution: SolutionDetail = {
  id: 'sol-001',
  name: 'Identity Bridge',
  version: '1.2.0',
  maturity: 'mvp',
  description: 'AD-to-Keycloak federation adapter',
  graph: { nodes: [], adapters: [] },
}

const mockFormData: DeployFormData = {
  keycloakRealm: 'gdit-internal',
  keycloakUrl: 'https://keycloak.internal',
  adDomain: 'corp.gdit.com',
  replicaCount: '2',
  classification: 'none',
  deploymentTarget: 'on-prem',
  dataDescription: 'Internal identity federation — no CUI.',
}

describe('Step3Confirm', () => {
  const noop = () => undefined

  describe('deployment summary', () => {
    it('shows the solution name', () => {
      render(
        <Step3Confirm
          solution={mockSolution}
          formData={mockFormData}
          onBack={noop}
          onConfirm={noop}
        />,
      )
      expect(screen.getByText('Identity Bridge')).toBeInTheDocument()
    })

    it('shows the selected classification', () => {
      render(
        <Step3Confirm
          solution={mockSolution}
          formData={mockFormData}
          onBack={noop}
          onConfirm={noop}
        />,
      )
      const summary = screen.getByTestId('deploy-summary')
      expect(within(summary).getByText('none')).toBeInTheDocument()
    })

    it('shows the deployment target', () => {
      render(
        <Step3Confirm
          solution={mockSolution}
          formData={mockFormData}
          onBack={noop}
          onConfirm={noop}
        />,
      )
      const summary = screen.getByTestId('deploy-summary')
      expect(within(summary).getByText('on-prem')).toBeInTheDocument()
    })
  })

  describe('audit event preview', () => {
    it('renders the Z-AUDIT preview section', () => {
      render(
        <Step3Confirm
          solution={mockSolution}
          formData={mockFormData}
          onBack={noop}
          onConfirm={noop}
        />,
      )
      expect(screen.getByTestId('audit-preview')).toBeInTheDocument()
    })

    it('shows the deploy.solution action', () => {
      render(
        <Step3Confirm
          solution={mockSolution}
          formData={mockFormData}
          onBack={noop}
          onConfirm={noop}
        />,
      )
      expect(screen.getByText('deploy.solution')).toBeInTheDocument()
    })

    it('shows the Z-AUDIT label', () => {
      render(
        <Step3Confirm
          solution={mockSolution}
          formData={mockFormData}
          onBack={noop}
          onConfirm={noop}
        />,
      )
      expect(screen.getByText(/Z-AUDIT event preview/i)).toBeInTheDocument()
    })
  })
})
