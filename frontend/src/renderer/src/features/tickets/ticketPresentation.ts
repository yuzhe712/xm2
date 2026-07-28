import type { TicketStatus } from '../../types/tickets'

export const statusLabels: Record<TicketStatus, string> = {
  pending: '待受理',
  open: '待认领',
  in_progress: '处理中',
  resolved: '待确认',
  closed: '已关闭',
  cancelled: '已取消',
}

export function formatDate(value?: string | null): string {
  if (!value) return '未设置'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}

export function isOverdue(value?: string | null): boolean {
  return Boolean(value && new Date(value).getTime() < Date.now())
}
