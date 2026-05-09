import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { NavRail } from '../components/layout/NavRail'

const renderWithRouter = (ui: React.ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>)

describe('NavRail', () => {
  it('renders all four navigation items', () => {
    renderWithRouter(<NavRail stage={1} />)
    expect(screen.getByText('Catalog')).toBeInTheDocument()
    expect(screen.getByText('Deployments')).toBeInTheDocument()
    expect(screen.getByText('Audit')).toBeInTheDocument()
    expect(screen.getByText('Stage Gate')).toBeInTheDocument()
  })

  it('displays the current stage badge', () => {
    renderWithRouter(<NavRail stage={1} />)
    expect(screen.getByText('S1')).toBeInTheDocument()
  })

  it('renders navigation as a landmark nav element', () => {
    renderWithRouter(<NavRail stage={1} />)
    expect(screen.getByRole('navigation')).toBeInTheDocument()
  })

  it('links catalog item to the catalog route', () => {
    renderWithRouter(<NavRail stage={1} />)
    expect(screen.getByRole('link', { name: /catalog/i })).toHaveAttribute('href', '/')
  })
})
