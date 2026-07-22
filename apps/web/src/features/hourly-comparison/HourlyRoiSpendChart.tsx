import { useMemo } from 'react'
import type { EChartsType } from 'echarts/core'
import { ECharts } from '@/components/ECharts'
import type { HourlyChartType, HourlyComparisonResponse } from '@/types/hourlyComparison'
import { buildHourlyChartOption } from './hourlyComparisonChart'

export function HourlyRoiSpendChart({
  data,
  chartType,
  selectedHour,
  showAllLabels,
  showRangeBand,
  activeSeriesKey,
  onHourClick,
  onChartReady,
}: {
  data: HourlyComparisonResponse
  chartType: HourlyChartType
  selectedHour: string | null
  showAllLabels: boolean
  showRangeBand: boolean
  activeSeriesKey: string | null
  onHourClick: (hour: string) => void
  onChartReady?: (chart: EChartsType) => void
}) {
  const option = useMemo(
    () =>
      buildHourlyChartOption(
        data,
        chartType,
        selectedHour,
        showAllLabels,
        showRangeBand,
        activeSeriesKey,
      ),
    [activeSeriesKey, chartType, data, selectedHour, showAllLabels, showRangeBand],
  )
  return (
    <ECharts
      option={option}
      notMerge
      lazyUpdate
      className="hourly-roi-spend-chart"
      opts={{ renderer: 'canvas' }}
      onChartReady={onChartReady}
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
