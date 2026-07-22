import type { EChartsCoreOption as EChartsOption } from 'echarts/core'
import { ECharts } from '@/components/ECharts'
import { chartPalette, chartSemanticColors } from '@/theme/chartTheme'
import type { TimelineGroup, TimelineSeries } from '@/types/dashboard'

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
    series: series.map((item, index) => ({
      name: item.name,
      type: 'line',
      smooth: true,
      showSymbol: item.data.length < 60,
      symbolSize: 7,
      lineStyle: { width: 2 },
      itemStyle: { color: colors[index % colors.length] },
      data: item.data.map((value) => (value === null ? null : Number(value))),
      connectNulls: false,
    })),
  }
  return (
    <ECharts
      option={option}
      notMerge
      className="metric-chart"
      onEvents={{
        click: (params: { dataIndex: number; seriesIndex: number }) => {
          const clickedSeries = series[params.seriesIndex]
          if (clickedSeries) onPointClick(params.dataIndex, clickedSeries)
        },
      }}
    />
  )
}
