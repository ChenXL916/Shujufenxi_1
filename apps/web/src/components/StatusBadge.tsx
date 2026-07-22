import type { ReactNode } from 'react'

export type StatusTone = 'positive' | 'info' | 'warning' | 'negative' | 'neutral'

export function StatusBadge({
  tone,
  children,
  title,
}: {
  tone: StatusTone
  children: ReactNode
  title?: string
}) {
  return (
    <span className={`status-badge status-badge-${tone}`} role="status" title={title}>
      <span className="status-badge-dot" aria-hidden="true" />
      <span>{children}</span>
    </span>
  )
}
