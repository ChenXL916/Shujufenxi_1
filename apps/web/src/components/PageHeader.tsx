import { Typography } from 'antd'
import type { ReactNode } from 'react'
import { ResponsiveActions } from './ResponsiveActions'

interface Props {
  title: string
  description: string
  actions?: ReactNode
  eyebrow?: string
}

export function PageHeader({ title, description, actions, eyebrow }: Props) {
  return (
    <div className="page-heading">
      <div className="page-heading-copy">
        {eyebrow ? <span className="page-eyebrow">{eyebrow}</span> : null}
        <Typography.Title level={3} title={title}>
          {title}
        </Typography.Title>
        <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
      </div>
      {actions ? <ResponsiveActions>{actions}</ResponsiveActions> : null}
    </div>
  )
}
