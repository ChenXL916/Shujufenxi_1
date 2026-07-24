import type { EChartsCoreOption as EChartsOption } from 'echarts/core'
import { ECharts } from '@/components/ECharts'
import { chartPalette, chartSemanticColors } from '@/theme/chartTheme'
import type { TimelineGroup, TimelineSeries } from '@/types/dashboard'
import { createLinePointHitTarget } from '@/utils/chartHitTarget'

const colors = chartPalette

export function MetricChart({
  group,
  series,
  onPointClick,
}: {
  group: TimelineGroup
  series: TimelineSeries[]
  onPointClick: (index: number, series: TimelineSeries) => void
}) {
  const values = series.map((item) =>
    item.data.map((value) => (value === null ? null : Number(value))),
  )
  const visibleSeries = series.map((item, index) => ({
    name: item.name,
    type: 'line' as const,
    smooth: true,
    showSymbol: item.data.length < 60,
    symbolSize: 7,
    lineStyle: { width: 2 },
    itemStyle: { color: colors[index % colors.length] },
    data: values[index],
    connectNulls: false,
  }))
  const hitTargets = series.map((item, index) =>
    createLinePointHitTarget({
      id: `timeline-hit-${index}`,
      name: item.name,
      data: values[index] ?? [],
      color: colors[index % colors.length] ?? colors[0] ?? '#1677ff',
    }),
  )
  const option: EChartsOption = {
    color: colors,
    animationDuration: 350,
    grid: { left: 64, right: 28, top: 52, bottom: 92 },
    legend: { top: 8, type: 'scroll' },
    toolbox: {
      right: 8,
      feature: {
        dataZoom: {},
        restore: {},
        saveAsImage: {
          name: `${group.group_label}-小时趋势`,
          backgroundColor: chartSemanticColors.canvas,
        },
      },
    },
    tooltip: { trigger: 'axis', confine: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 12 }],
    xAxis: {
      type: 'category',
      data: group.x_items.map((item) => item.label),
      axisLabel: { interval: 0, lineHeight: 16, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: series[0]?.unit ?? '',
      scale: true,
      splitLine: { lineStyle: { color: chartSemanticColors.grid, type: 'dashed' } },
    },
    series: [...visibleSeries, ...hitTargets],
  }
  return (
    <ECharts
      option={option}
      notMerge
      className="metric-chart"
      onEvents={{
        click: (params: { dataIndex: number; seriesId?: string; seriesIndex: number }) => {
          const hitIndex = params.seriesId?.match(/^timeline-hit-(\d+)$/)?.[1]
          const sourceIndex = hitIndex === undefined ? params.seriesIndex : Number(hitIndex)
          const clickedSeries = series[sourceIndex]
          if (clickedSeries) onPointClick(params.dataIndex, clickedSeries)
        },
      }}
    />
  )
}
