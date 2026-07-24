import type { LineSeriesOption } from 'echarts/charts'

export const CHART_POINT_HIT_SIZE = 24

export function createLinePointHitTarget({
  id,
  name,
  data,
  color,
  xAxisIndex,
  yAxisIndex,
}: {
  id: string
  name: string
  data: Array<number | null>
  color: string
  xAxisIndex?: number
  yAxisIndex?: number
}): LineSeriesOption {
  return {
    id,
    name,
    type: 'line',
    data,
    xAxisIndex,
    yAxisIndex,
    connectNulls: false,
    showSymbol: true,
    symbol: 'circle',
    symbolSize: CHART_POINT_HIT_SIZE,
    cursor: 'pointer',
    animation: false,
    z: 20,
    lineStyle: { width: 0, opacity: 0 },
    itemStyle: {
      color: 'rgba(255, 255, 255, 0.001)',
      borderColor: 'rgba(255, 255, 255, 0.001)',
      borderWidth: 0,
    },
    emphasis: {
      focus: 'self',
      scale: true,
      itemStyle: {
        color: 'rgba(255, 255, 255, 0.92)',
        borderColor: color,
        borderWidth: 2,
        shadowBlur: 8,
        shadowColor: 'rgba(15, 23, 42, 0.18)',
      },
    },
    blur: {
      itemStyle: {
        opacity: 0.12,
      },
    },
    tooltip: { show: false },
  }
}
