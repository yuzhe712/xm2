import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EvidencePanel } from './EvidencePanel'
import type { Evidence } from '../types/tickets'

const evidence: Evidence[] = [
  {
    evidence_id: 'ev_ticket_input_001',
    source_type: 'ticket_input',
    source_id: 'TCK-001',
    source_name: '用户输入工单',
    service: 'payment-service',
    metric_name: 'timeout_rate',
    value: 18.5,
    unit: '%',
    quality: 'fresh',
    data_mode: 'mock',
    summary: '支付服务超时',
  },
]

describe('EvidencePanel', () => {
  it('renders expandable evidence details and selected state', () => {
    const onSelect = vi.fn()
    render(
      <EvidencePanel
        evidence={evidence}
        selectedEvidenceId="ev_ticket_input_001"
        onSelectEvidence={onSelect}
      />,
    )

    expect(screen.getByText('ev_ticket_input_001')).toBeInTheDocument()
    expect(screen.getByText('ticket_input / 用户输入工单')).toBeInTheDocument()
    expect(screen.getByText('timeout_rate: 18.5%')).toBeInTheDocument()
    fireEvent.click(screen.getByText('ev_ticket_input_001'))
    expect(onSelect).toHaveBeenCalledWith('ev_ticket_input_001')
  })
})
