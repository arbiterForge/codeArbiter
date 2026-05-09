import { render, screen } from '@testing-library/react'
import { AuthBypassBanner } from '../components/auth/AuthBypassBanner'

describe('AuthBypassBanner', () => {
  it('renders an alert when bypass is active', () => {
    render(<AuthBypassBanner active={true} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('displays the AUTH BYPASS ACTIVE warning', () => {
    render(<AuthBypassBanner active={true} />)
    expect(screen.getByText(/AUTH BYPASS ACTIVE/i)).toBeInTheDocument()
  })

  it('warns that bypass must not be used outside dev', () => {
    render(<AuthBypassBanner active={true} />)
    expect(screen.getByText(/NOT FOR USE OUTSIDE DEV/i)).toBeInTheDocument()
  })

  it('renders nothing when bypass is inactive', () => {
    const { container } = render(<AuthBypassBanner active={false} />)
    expect(container).toBeEmptyDOMElement()
  })
})
