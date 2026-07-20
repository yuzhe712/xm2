import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TicketHistoryList } from './TicketHistoryList'

describe('TicketHistoryList', () => {
  it('renders an empty state without fake rows', () => {
    render(<TicketHistoryList items={[]} loading={false} total={0} onSelect={vi.fn()} />)

    expect(screen.getByText('暂无历史工单。')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: '历史工单请求列表' })).not.toBeInTheDocument()
  })

  it('renders custom title and empty text', () => {
    render(
      <TicketHistoryList
        items={[]}
        loading={false}
        total={0}
        title="请求列表"
        emptyText="当前筛选条件下暂无请求。"
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByText('请求列表')).toBeInTheDocument()
    expect(screen.getByText('当前筛选条件下暂无请求。')).toBeInTheDocument()
  })

  it('renders persisted ticket rows with mock badge', () => {
    render(
      <TicketHistoryList
        items={[
          {
            ticket_id: 'TCK-20260715-ABCDEF12',
            desk_id: 'ops',
            latest_run_id: 'RUN-20260715-1234ABCD',
            created_at: 'now',
            updated_at: 'now',
            data_mode: 'mock',
            status: 'completed',
            ticket_status: 'resolved',
            summary: '支付服务超时',
            affected_service: 'payment-service',
            priority: 'P1',
            report_title: '支付服务报告',
          },
        ]}
        loading={false}
        total={1}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByRole('table', { name: '历史工单请求列表' })).toBeInTheDocument()
    expect(screen.getByText('TCK-20260715-ABCDEF12')).toBeInTheDocument()
    expect(screen.getByText('支付服务报告')).toBeInTheDocument()
    expect(screen.getByText('已解决')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('P1')).toBeInTheDocument()
    expect(screen.getByText('payment-service')).toBeInTheDocument()
    expect(screen.getByText('模拟数据 mock')).toBeInTheDocument()
  })

  it('selects a persisted ticket from the table action', () => {
    const onSelect = vi.fn()
    render(
      <TicketHistoryList
        items={[
          {
            ticket_id: 'TCK-20260715-ABCDEF12',
            desk_id: 'ops',
            latest_run_id: 'RUN-20260715-1234ABCD',
            created_at: 'now',
            updated_at: 'now',
            data_mode: 'mock',
            status: 'completed',
            ticket_status: 'resolved',
            summary: '支付服务超时',
          },
        ]}
        loading={false}
        total={1}
        selectedTicketId="TCK-20260715-ABCDEF12"
        onSelect={onSelect}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '查看' }))

    expect(onSelect).toHaveBeenCalledWith('TCK-20260715-ABCDEF12')
  })

  it('renders failed and cancelled status labels', () => {
    render(
      <TicketHistoryList
        items={[
          {
            ticket_id: 'TCK-20260715-ABCDEF12',
            desk_id: 'ops',
            latest_run_id: 'RUN-20260715-1234ABCD',
            created_at: 'now',
            updated_at: 'now',
            data_mode: 'mock',
            status: 'failed',
            ticket_status: 'open',
            summary: '支付服务超时',
          },
          {
            ticket_id: 'TCK-20260715-ABCDEF13',
            desk_id: 'support',
            latest_run_id: 'RUN-20260715-1234ABCE',
            created_at: 'now',
            updated_at: 'now',
            data_mode: 'mock',
            status: 'cancelled',
            ticket_status: 'cancelled',
            summary: '用户取消处理',
          },
        ]}
        loading={false}
        total={2}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getAllByText('已取消')).toHaveLength(2)
  })
})
