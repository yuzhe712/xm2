import { useParams } from 'react-router-dom'
import { TicketDetailView } from '../../features/tickets/TicketDetailView'

export function EmployeeTicketDetailPage(): JSX.Element {
  const { ticketId = '' } = useParams()
  return <TicketDetailView ticketId={ticketId} role="employee" backTo="/employee/tickets" />
}
