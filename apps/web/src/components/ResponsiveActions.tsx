import type { ReactNode } from 'react'

export function ResponsiveActions({
  children,
  label = '页面操作',
  className = '',
}: {
  children: ReactNode
  label?: string
  className?: string
}) {
  return (
    <div
      className={`responsive-actions${className ? ` ${className}` : ''}`}
      role="group"
      aria-label={label}
    >
      {children}
    </div>
  )
}
