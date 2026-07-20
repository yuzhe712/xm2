interface NotificationChannelResult {
  channel: string
  status: string
  message?: string | null
}

interface NotificationStatusProps {
  notification: Record<string, unknown>
}

const CHANNEL_LABELS: Record<string, string> = {
  dingtalk: '钉钉群机器人',
  email: '邮件',
  wechat: '企业微信',
  feishu: '飞书',
}

function labelFor(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel
}

export default function NotificationStatus({ notification }: NotificationStatusProps) {
  const channels = notification.channels as NotificationChannelResult[] | undefined
  if (!channels || channels.length === 0) {
    return null
  }

  return (
    <div className="notification-status" aria-label="通知发送状态">
      {channels.map((ch, idx) => (
        <span
          key={idx}
          className={`notification-badge notification-badge--${ch.status}`}
          title={ch.message ?? undefined}
        >
          {ch.status === 'sent'
            ? `✉ 已发送至${labelFor(ch.channel)}`
            : ch.status === 'skipped'
              ? `✉ ${labelFor(ch.channel)}未配置，跳过通知`
              : `✉ ${labelFor(ch.channel)}发送失败`}
        </span>
      ))}
    </div>
  )
}
