import type { SampleTicket } from '../data/sampleTickets'

interface SampleTicketListProps {
  tickets: SampleTicket[]
  onSelect: (ticket: SampleTicket) => void
}

export function SampleTicketList({ tickets, onSelect }: SampleTicketListProps): JSX.Element {
  return (
    <section className="panel sample-panel">
      <h2>示例工单模板</h2>
      <div className="sample-list">
        {tickets.map((ticket) => (
          <button key={ticket.id} className="sample-card" type="button" onClick={() => onSelect(ticket)}>
            <strong>{ticket.title}</strong>
            <span>{ticket.text}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
