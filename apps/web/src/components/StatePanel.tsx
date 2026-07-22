import { Alert, Button, Empty, Skeleton } from 'antd'
import type { ReactNode } from 'react'

function StatePanelFrame({
  kind,
  children,
  busy = false,
}: {
  kind: 'loading' | 'empty' | 'error'
  children: ReactNode
  busy?: boolean
}) {
  return (
    <div
      className={`state-panel state-panel-${kind}`}
      role={kind === 'error' ? undefined : 'status'}
      aria-live="polite"
      aria-busy={busy}
    >
      {children}
    </div>
  )
}

export function LoadingPanel() {
  return (
    <StatePanelFrame kind="loading" busy>
      <Skeleton active paragraph={{ rows: 6 }} />
    </StatePanelFrame>
  )
}

export function EmptyPanel({ scheduleOnly = false }: { scheduleOnly?: boolean }) {
  return (
    <StatePanelFrame kind="empty">
      <Empty
        description={
          scheduleOnly
            ? '当前直播间已有排班数据，但暂无实绩数据。'
            : '当前筛选条件下暂无实际数据，请调整日期、直播间或检查数据是否已同步。'
        }
      />
    </StatePanelFrame>
  )
}

export function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <StatePanelFrame kind="error">
      <Alert
        type="error"
        showIcon
        title="数据加载失败"
        description="请检查 API 服务、数据库同步状态或稍后重试。"
        action={<Button onClick={onRetry}>重试</Button>}
      />
    </StatePanelFrame>
  )
}
