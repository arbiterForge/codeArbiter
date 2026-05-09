import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CatalogPage } from '../pages/CatalogPage'

const renderWithRouter = (ui: React.ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>)

describe('CatalogPage', () => {
  describe('empty state', () => {
    it('shows the no-solutions-yet message', () => {
      render(<CatalogPage solutions={[]} loading={false} />)
      expect(screen.getByText(/no solutions yet/i)).toBeInTheDocument()
    })

    it('shows the /new-node call to action', () => {
      render(<CatalogPage solutions={[]} loading={false} />)
      expect(screen.getByText(/\/new-node/i)).toBeInTheDocument()
    })

    it('empty state has an accessible heading', () => {
      render(<CatalogPage solutions={[]} loading={false} />)
      expect(screen.getByRole('heading', { name: /no solutions yet/i })).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('shows the skeleton loader while fetching', () => {
      render(<CatalogPage solutions={[]} loading={true} />)
      expect(screen.getByTestId('catalog-skeleton')).toBeInTheDocument()
    })

    it('does not show the empty state while loading', () => {
      render(<CatalogPage solutions={[]} loading={true} />)
      expect(screen.queryByText(/no solutions yet/i)).not.toBeInTheDocument()
    })
  })

  describe('populated state', () => {
    const mockSolutions = [
      {
        id: 'sol-001',
        name: 'Identity Bridge',
        version: '1.2.0',
        maturity: 'mvp' as const,
        description: 'AD-to-Keycloak federation adapter',
      },
    ]

    it('renders solution cards when solutions exist', () => {
      renderWithRouter(<CatalogPage solutions={mockSolutions} loading={false} />)
      expect(screen.getByText('Identity Bridge')).toBeInTheDocument()
    })

    it('does not show the empty state when solutions exist', () => {
      renderWithRouter(<CatalogPage solutions={mockSolutions} loading={false} />)
      expect(screen.queryByText(/no solutions yet/i)).not.toBeInTheDocument()
    })
  })
})
