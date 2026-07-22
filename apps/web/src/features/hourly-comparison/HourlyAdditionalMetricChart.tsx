import { useMemo } from 'react'
import { ECharts } from '@/components/ECharts'
import type {
  HourlyChartType,
  HourlyComparisonResponse,
  HourlyMetricOption,
} from '@/types/hourlyComparison'
import { buildAdditionalMetricOption } from './additionalMetricChartOption'

export function HourlyAdditionalMetricChart({
  data,
  metric,
  chartType,
  selectedHour,
  showAllLabels,
  onHourClick,
}: {
  data: HourlyComparisonResponse
  metric: HourlyMetricOption
  chartType: HourlyChartType
  selectedHour: string | null
  showAllLabels: boolean
  onHourClick: (hour: string) => void
}) {
  const option = useMemo(
    () => buildAdditionalMetricOption(data, metric, chartType, selectedHour, showAllLabels),
    [chartType, data, metric, selectedHour, showAllLabels],
  )

  return (
    <ECharts
      option={option}
      notMerge
      lazyUpdate
      className="hourly-additional-metric-chart"
      opts={{ renderer: 'canvas' }}
      onEvents={{
        click: (parameters: { dataIndex?: number }) => {
          if (typeof parameters.dataIndex !== 'number') return
          const hour = data.hours[parameters.dataIndex]
          if (hour) onHourClick(hour.key)
        },
      }}
    />
  )
}
