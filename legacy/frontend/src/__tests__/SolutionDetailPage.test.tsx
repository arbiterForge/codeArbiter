import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SolutionDetailPage } from '../pages/SolutionDetailPage'
import type { SolutionDetail } from '../types/solution'

const baseSolution: SolutionDetail = {
  id: 'sol-001',
  name: 'Identity Bridge',
  version: '1.2.0',
  maturity: 'mvp',
  description: 'AD-to-Keycloak federation adapter',
  graph: { nodes: [], adapters: [] },
}

const withNodes: SolutionDetail = {
  ...baseSolution,
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

const renderPage = (solution: SolutionDetail) =>
  render(
    <MemoryRouter>
      <SolutionDetailPage solution={solution} />
    </MemoryRouter>,
  )

describe('SolutionDetailPage', () => {
  describe('metadata panel', () => {
    it('renders the solution name', () => {
      renderPage(baseSolution)
      expect(screen.getByText('Identity Bridge')).toBeInTheDocument()
    })

    it('renders the version', () => {
      renderPage(baseSolution)
      expect(screen.getByText('1.2.0')).toBeInTheDocument()
    })

    it('renders the maturity badge', () => {
      renderPage(baseSolution)
      expect(screen.getByText('mvp')).toBeInTheDocument()
    })

    it('renders the description', () => {
      renderPage(baseSolution)
      expect(screen.getByText('AD-to-Keycloak federation adapter')).toBeInTheDocument()
    })
  })

  describe('deploy button', () => {
    it('is disabled when the solution has no nodes', () => {
      renderPage(baseSolution)
      expect(screen.getByRole('button', { name: /deploy/i })).toBeDisabled()
    })

    it('carries an explanatory title when disabled', () => {
      renderPage(baseSolution)
      const btn = screen.getByRole('button', { name: /deploy/i })
      expect(btn).toHaveAttribute('title', expect.stringMatching(/node/i))
    })

    it('is enabled when nodes exist', () => {
      renderPage(withNodes)
      expect(screen.getByRole('button', { name: /deploy/i })).not.toBeDisabled()
    })
  })

  describe('graph canvas', () => {
    it('renders the graph container', () => {
      renderPage(baseSolution)
      expect(screen.getByTestId('solution-graph')).toBeInTheDocument()
    })

    it('shows the empty graph message when no nodes exist', () => {
      renderPage(baseSolution)
      expect(screen.getByText(/no nodes defined/i)).toBeInTheDocument()
    })
  })
})
