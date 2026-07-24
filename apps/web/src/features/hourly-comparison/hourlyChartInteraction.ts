import type { EChartsType } from 'echarts/core'

export function focusHourlySeries(chart: EChartsType, seriesName: string | undefined) {
  if (!seriesName) return
  chart.dispatchAction({ type: 'downplay' })
  chart.dispatchAction({ type: 'highlight', seriesName })
}

export function clearHourlySeriesFocus(chart: EChartsType) {
  chart.dispatchAction({ type: 'downplay' })
}
