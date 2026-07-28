import { useParams } from 'react-router-dom'
import { TicketDetailView } from '../../features/tickets/TicketDetailView'

export function OperatorTicketDetailPage(): JSX.Element {
  const { ticketId = '' } = useParams()
  return <TicketDetailView ticketId={ticketId} role="operator" backTo="/operator/queue" />
}
