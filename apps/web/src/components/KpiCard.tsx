import { ArrowDownOutlined, ArrowUpOutlined, MinusOutlined } from '@ant-design/icons'
import { Card, Tooltip, Typography } from 'antd'
import type { KpiPayload } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

export function KpiCard({
  item,
  onClick,
  selected = false,
}: {
  item: KpiPayload
  onClick: () => void
  selected?: boolean
}) {
  const growth =
    item.comparison.growth_percent === null ? null : Number(item.comparison.growth_percent)
  const inverse = item.direction === 'lower_better'
  const positive = growth !== null && (inverse ? growth < 0 : growth > 0)
  const spendOnly = item.metric_key === 'period_spend' || item.metric_key.endsWith('_spend')
  const tone =
    growth === null || growth === 0
      ? 'neutral'
      : spendOnly
        ? 'warning'
        : positive
          ? 'positive'
          : 'negative'
  const trendLabel =
    growth === null
      ? '无有效基准'
      : growth === 0
        ? '持平 0.0%'
        : `${growth > 0 ? '上涨' : '下降'} ${Math.abs(growth).toFixed(1)}%`
  const Icon =
    growth === null || growth === 0
      ? MinusOutlined
      : growth > 0
        ? ArrowUpOutlined
        : ArrowDownOutlined
  const displayValue = formatMetric(item.value, item.unit, item.precision)
  const fullValueLabel = `${item.name}：${displayValue}`

  return (
    <Card
      hoverable
      className={`kpi-card${selected ? ' selected' : ''}`}
      onClick={onClick}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      onKeyDown={(event) => {
        if (event.repeat) return
        if (event.key === 'Enter') onClick()
        if (event.key === ' ') event.preventDefault()
      }}
      onKeyUp={(event) => {
        if (event.key === ' ') onClick()
      }}
    >
      <div className="kpi-card-header">
        <Tooltip title={item.name} mouseEnterDelay={0.25}>
          <Typography.Text type="secondary" className="kpi-label" title={item.name}>
            {item.name}
          </Typography.Text>
        </Tooltip>
      </div>
      <Tooltip title={fullValueLabel} mouseEnterDelay={0.2}>
        <Typography.Title
          level={3}
          className="kpi-value"
          aria-label={fullValueLabel}
          title={displayValue}
        >
          {displayValue}
        </Typography.Title>
      </Tooltip>
      <div className="kpi-meta">
        <Tooltip title={item.comparison.explanation}>
          <div className={`kpi-comparison ${tone}`}>
            <Icon aria-hidden="true" /> <span className="kpi-trend-label">{trendLabel}</span>
          </div>
        </Tooltip>
        <Typography.Text className="kpi-baseline" type="secondary">
          基准 {formatMetric(item.comparison.baseline_value, item.unit, item.precision)}
        </Typography.Text>
      </div>
    </Card>
  )
}
