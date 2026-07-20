export interface SampleTicket {
  id: string
  title: string
  text: string
}

export const sampleTickets: SampleTicket[] = [
  {
    id: 'payment-timeout',
    title: '支付服务超时告警',
    text: '线上支付服务出现超时告警，订单量从正常1000/min降到300/min',
  },
]
