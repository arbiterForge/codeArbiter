import { render, screen, fireEvent, within } from '@testing-library/react'
import { AuditLogPage } from '../pages/AuditLogPage'
import { MOCK_AUDIT_EVENTS } from '../loaders/auditLoader'

const renderPage = (events = MOCK_AUDIT_EVENTS) =>
  render(<AuditLogPage events={events} />)

describe('AuditLogPage', () => {
  describe('initial render', () => {
    it('shows the page heading', () => {
      renderPage()
      expect(screen.getByRole('heading', { name: /audit log/i })).toBeInTheDocument()
    })

    it('renders the search input', () => {
      renderPage()
      expect(screen.getByRole('textbox', { name: /search audit events/i })).toBeInTheDocument()
    })

    it('shows all mock events on initial load', () => {
      renderPage()
      expect(screen.getAllByTestId('audit-event-row')).toHaveLength(MOCK_AUDIT_EVENTS.length)
    })

    it('shows a live event count', () => {
      renderPage()
      expect(screen.getByTestId('event-count')).toHaveTextContent(`${MOCK_AUDIT_EVENTS.length}`)
    })
  })

  describe('search query', () => {
    it('filters events when outcome:failure is typed', () => {
      renderPage()
      fireEvent.change(screen.getByRole('textbox', { name: /search audit events/i }), {
        target: { value: 'outcome:failure' },
      })
      const rows = screen.getAllByTestId('audit-event-row')
      const failureEvents = MOCK_AUDIT_EVENTS.filter((e) => e.outcome === 'failure')
      expect(rows).toHaveLength(failureEvents.length)
    })

    it('filters events when action:deploy.* is typed', () => {
      renderPage()
      fireEvent.change(screen.getByRole('textbox', { name: /search audit events/i }), {
        target: { value: 'action:deploy.*' },
      })
      const rows = screen.getAllByTestId('audit-event-row')
      const deployEvents = MOCK_AUDIT_EVENTS.filter((e) => e.action.startsWith('deploy.'))
      expect(rows).toHaveLength(deployEvents.length)
    })

    it('filters by actor using actor:field syntax', () => {
      renderPage()
      fireEvent.change(screen.getByRole('textbox', { name: /search audit events/i }), {
        target: { value: 'actor:bhuff' },
      })
      const rows = screen.getAllByTestId('audit-event-row')
      const bhuffEvents = MOCK_AUDIT_EVENTS.filter((e) => e.actor.id === 'bhuff')
      expect(rows).toHaveLength(bhuffEvents.length)
    })

    it('filters by free text across action and actor fields', () => {
      renderPage()
      fireEvent.change(screen.getByRole('textbox', { name: /search audit events/i }), {
        target: { value: 'cardinal' },
      })
      const rows = screen.getAllByTestId('audit-event-row')
      const cardinalEvents = MOCK_AUDIT_EVENTS.filter((e) => e.actor.id === 't.cardinal')
      expect(rows).toHaveLength(cardinalEvents.length)
    })

    it('shows the empty state when no events match the query', () => {
      renderPage()
      fireEvent.change(screen.getByRole('textbox', { name: /search audit events/i }), {
        target: { value: 'action:nonexistent.event' },
      })
      expect(screen.getByTestId('audit-empty')).toBeInTheDocument()
    })

    it('restores all events when the query is cleared', () => {
      renderPage()
      const input = screen.getByRole('textbox', { name: /search audit events/i })
      fireEvent.change(input, { target: { value: 'outcome:failure' } })
      fireEvent.change(input, { target: { value: '' } })
      expect(screen.getAllByTestId('audit-event-row')).toHaveLength(MOCK_AUDIT_EVENTS.length)
    })
  })

  describe('quick filter chips', () => {
    it('clicking the Failure chip filters to failure events', () => {
      renderPage()
      fireEvent.click(screen.getByRole('button', { name: /^failure$/i }))
      const failureEvents = MOCK_AUDIT_EVENTS.filter((e) => e.outcome === 'failure')
      expect(screen.getAllByTestId('audit-event-row')).toHaveLength(failureEvents.length)
    })

    it('clicking the Denied chip filters to denied events', () => {
      renderPage()
      fireEvent.click(screen.getByRole('button', { name: /^denied$/i }))
      const deniedEvents = MOCK_AUDIT_EVENTS.filter((e) => e.outcome === 'denied')
      expect(screen.getAllByTestId('audit-event-row')).toHaveLength(deniedEvents.length)
    })

    it('clicking All clears the outcome filter', () => {
      renderPage()
      fireEvent.click(screen.getByRole('button', { name: /^failure$/i }))
      fireEvent.click(screen.getByRole('button', { name: /^all$/i }))
      expect(screen.getAllByTestId('audit-event-row')).toHaveLength(MOCK_AUDIT_EVENTS.length)
    })
  })

  describe('row expansion', () => {
    it('clicking a row expands the detail panel', () => {
      renderPage()
      fireEvent.click(screen.getAllByTestId('audit-event-row')[0])
      expect(screen.getByTestId('audit-event-detail')).toBeInTheDocument()
    })

    it('expanded panel shows the event_id', () => {
      renderPage()
      fireEvent.click(screen.getAllByTestId('audit-event-row')[0])
      const detail = screen.getByTestId('audit-event-detail')
      expect(within(detail).getByText(MOCK_AUDIT_EVENTS[0].event_id)).toBeInTheDocument()
    })

    it('expanded panel shows the source.request_id', () => {
      renderPage()
      fireEvent.click(screen.getAllByTestId('audit-event-row')[0])
      const detail = screen.getByTestId('audit-event-detail')
      expect(
        within(detail).getByText(MOCK_AUDIT_EVENTS[0].source.request_id),
      ).toBeInTheDocument()
    })

    it('clicking an expanded row collapses it', () => {
      renderPage()
      const row = screen.getAllByTestId('audit-event-row')[0]
      fireEvent.click(row)
      expect(row).toHaveAttribute('aria-expanded', 'true')
      fireEvent.click(row)
      expect(row).toHaveAttribute('aria-expanded', 'false')
    })
  })

  describe('empty state', () => {
    it('shows empty state when no events are passed', () => {
      renderPage([])
      expect(screen.getByTestId('audit-empty')).toBeInTheDocument()
    })
  })
})
