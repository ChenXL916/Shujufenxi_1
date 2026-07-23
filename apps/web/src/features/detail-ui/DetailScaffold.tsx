import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
  InfoCircleFilled,
} from '@ant-design/icons'
import { Tag, Typography } from 'antd'
import type { ReactNode } from 'react'

export type DetailTone = 'positive' | 'warning' | 'negative' | 'neutral' | 'info'

export interface DetailStatus {
  label: string
  tone: DetailTone
}

export interface DetailContextItem {
  key: string
  label: string
  value: ReactNode
  icon?: ReactNode
}

export interface DetailMetaItem {
  key: string
  label: string
  value: ReactNode
}

export interface DetailMetricItem {
  key: string
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: DetailTone
}

function accessibleText(value: ReactNode): string {
  if (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'bigint' ||
    typeof value === 'boolean'
  ) {
    return String(value)
  }
  return '详情数值'
}

export function DetailStatusTag({ status }: { status: DetailStatus }) {
  const icon =
    status.tone === 'positive' ? (
      <CheckCircleFilled aria-hidden />
    ) : status.tone === 'warning' ? (
      <ExclamationCircleFilled aria-hidden />
    ) : status.tone === 'negative' ? (
      <CloseCircleFilled aria-hidden />
    ) : status.tone === 'info' ? (
      <InfoCircleFilled aria-hidden />
    ) : null

  return (
    <Tag className={`detail-status-tag ${status.tone}`}>
      {icon}
      {status.label}
    </Tag>
  )
}

export function DetailHero({
  id,
  icon,
  iconTone = 'orange',
  eyebrow,
  title,
  badge,
  statuses,
  meta,
  contexts,
  supplementary = [],
}: {
  id: string
  icon: ReactNode
  iconTone?: 'orange' | 'blue' | 'purple'
  eyebrow: string
  title: ReactNode
  badge?: ReactNode
  statuses: DetailStatus[]
  meta?: ReactNode
  contexts: DetailContextItem[]
  supplementary?: DetailMetaItem[]
}) {
  return (
    <section className="detail-overview-card" aria-labelledby={id}>
      <div className="detail-overview-heading">
        <span className={`detail-hero-icon ${iconTone}`} aria-hidden>
          {icon}
        </span>
        <div className="detail-hero-copy">
          <Typography.Text className="detail-eyebrow">{eyebrow}</Typography.Text>
          <Typography.Title id={id} level={3}>
            {title}
          </Typography.Title>
        </div>
        {badge ? <Tag className="detail-kind-tag">{badge}</Tag> : null}
      </div>

      <div className="detail-status-row" aria-label="详情状态">
        {statuses.map((status) => (
          <DetailStatusTag key={`${status.tone}-${status.label}`} status={status} />
        ))}
        {meta ? <Typography.Text type="secondary">{meta}</Typography.Text> : null}
      </div>

      <div className="detail-context-grid">
        {contexts.map((item) => (
          <div className="detail-context-item" key={item.key}>
            <span>
              {item.icon}
              {item.label}
            </span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>

      {supplementary.length ? (
        <div className="detail-quality-grid">
          {supplementary.map((item) => (
            <div key={item.key}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export function DetailSectionHeading({
  id,
  icon,
  kicker,
  title,
  aside,
  compact = false,
}: {
  id: string
  icon?: ReactNode
  kicker: string
  title: ReactNode
  aside?: ReactNode
  compact?: boolean
}) {
  return (
    <div className={`detail-section-heading${compact ? ' compact' : ''}`}>
      <div>
        <Typography.Text className="detail-section-kicker">
          {icon}
          {kicker}
        </Typography.Text>
        <Typography.Title id={id} level={4}>
          {title}
        </Typography.Title>
      </div>
      {aside ? <Typography.Text type="secondary">{aside}</Typography.Text> : null}
    </div>
  )
}

export function DetailMetricGrid({
  items,
  wide = false,
}: {
  items: DetailMetricItem[]
  wide?: boolean
}) {
  return (
    <div className={`detail-metric-grid${wide ? ' detail-metric-grid-wide' : ''}`}>
      {items.map((item) => (
        <article className={`detail-metric-tile${item.tone ? ` ${item.tone}` : ''}`} key={item.key}>
          <div className="detail-metric-meta">
            <span>{item.label}</span>
            {item.hint ? <small>{item.hint}</small> : null}
          </div>
          <strong
            className="detail-metric-value"
            aria-label={`${item.label}：${accessibleText(item.value)}`}
          >
            {item.value}
          </strong>
        </article>
      ))}
    </div>
  )
}
