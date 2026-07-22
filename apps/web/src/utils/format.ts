import type { MetricOption, TimelineSeries } from '@/types/dashboard'

export function formatMetric(value: string | number | null, unit: string, precision = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const number = Number(value)
  if (unit === 'percent') return `${(number * 100).toFixed(precision)}%`
  if (unit === 'currency')
    return `¥${number.toLocaleString('zh-CN', { minimumFractionDigits: precision, maximumFractionDigits: precision })}`
  if (unit === 'count') return Math.round(number).toLocaleString('zh-CN')
  return number.toFixed(precision)
}

export function formatRoiChange(
  currentValue: string | number | null,
  deltaValue: string | number | null,
  growthPercent: string | number | null,
) {
  if (currentValue === null || currentValue === undefined) return '待当前实绩'
  const delta = Number(deltaValue)
  const growth = Number(growthPercent)
  if (
    deltaValue === null ||
    growthPercent === null ||
    Number.isNaN(delta) ||
    Number.isNaN(growth)
  ) {
    return '—'
  }
  if (delta < 0) return `下降 ${Math.abs(delta).toFixed(2)}（${Math.abs(growth).toFixed(2)}%）`
  if (delta > 0) return `提升 ${delta.toFixed(2)}（${growth.toFixed(2)}%）`
  return '持平 0.00（0.00%）'
}

export function groupSeriesByUnit(series: TimelineSeries[]) {
  return series.reduce<Record<string, TimelineSeries[]>>((groups, item) => {
    ;(groups[item.unit] ??= []).push(item)
    return groups
  }, {})
}

export function metricLabel(metric: MetricOption) {
  return `${metric.name} · ${metric.scope === 'period' ? '时段' : metric.scope === 'cumulative' ? '累计末值' : metric.scope}`
}
