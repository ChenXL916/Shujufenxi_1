import type { EChartsCoreOption as EChartsOption } from 'echarts/core'
import type { BarSeriesOption, CandlestickSeriesOption, LineSeriesOption } from 'echarts/charts'
import type {
  BusinessKlinePayload,
  HourlyChartType,
  HourlyComparisonResponse,
  HourlyMetricOption,
  NumericValue,
} from '@/types/hourlyComparison'
import { chartComparisonPalette, chartPalette, chartSemanticColors } from '@/theme/chartTheme'

type MetricSeries = BarSeriesOption | CandlestickSeriesOption | LineSeriesOption

const COLORS = chartPalette

function numberOrNull(value: NumericValue): number | null {
  if (value === null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function candle(value: BusinessKlinePayload | null | undefined): [number, number, number, number] {
  if (!value) return [Number.NaN, Number.NaN, Number.NaN, Number.NaN]
  const values = [value.open, value.close, value.low, value.high].map(numberOrNull)
  return values.some((item) => item === null)
    ? [Number.NaN, Number.NaN, Number.NaN, Number.NaN]
    : (values as [number, number, number, number])
}

function selectedMarkLine(hour: string | null): Array<Record<string, unknown>> {
  return hour
    ? [
        {
          name: '当前选中小时',
          xAxis: hour,
          lineStyle: { color: chartSemanticColors.muted, type: 'dotted', width: 1 },
          label: { formatter: hour },
        },
      ]
    : []
}

export function buildAdditionalMetricOption(
  data: HourlyComparisonResponse,
  metric: HourlyMetricOption,
  chartType: HourlyChartType,
  selectedHour: string | null,
  showAllLabels: boolean,
): EChartsOption {
  const hours = data.hours.map((hour) => hour.key)
  const series: MetricSeries[] = []

  data.series.slice(0, 6).forEach((item, index) => {
    const color = COLORS[index % COLORS.length]
    const currentValues = item.points.map((point) =>
      numberOrNull(point.current.metrics[metric.key] ?? null),
    )
    const baselineValues = item.points.map((point) =>
      numberOrNull(point.comparison?.metrics[metric.key] ?? null),
    )

    if (chartType === 'business_kline') {
      series.push({
        name: `${item.series_name} 当前${metric.name}`,
        type: 'candlestick',
        data: item.points.map((point) => candle(point.current.metric_ohlc[metric.key])),
        itemStyle: {
          color: chartSemanticColors.positive,
          color0: chartSemanticColors.negative,
          borderColor: chartSemanticColors.positive,
          borderColor0: chartSemanticColors.negative,
        },
        markLine: { symbol: 'none', data: selectedMarkLine(selectedHour) },
      })
      if (data.comparison_period) {
        series.push({
          name: `${item.series_name} 上一周期${metric.name}`,
          type: 'line',
          data: baselineValues,
          connectNulls: false,
          symbol: 'none',
          lineStyle: {
            color: chartComparisonPalette[index % chartComparisonPalette.length],
            type: 'dashed',
            width: 1.5,
          },
        })
      }
      return
    }

    const current: LineSeriesOption | BarSeriesOption = {
      name: `${item.series_name} 当前${metric.name}`,
      type: chartType,
      data: currentValues,
      itemStyle: { color },
      label: {
        show: showAllLabels,
        position: 'top',
        formatter: ({ value }: { value?: unknown }) =>
          typeof value === 'number' ? value.toFixed(metric.precision) : '',
      },
      markLine: { symbol: 'none', data: selectedMarkLine(selectedHour) },
      ...(chartType === 'line'
        ? { connectNulls: false, symbol: 'circle', symbolSize: 6, lineStyle: { color, width: 2 } }
        : {}),
    }
    series.push(current)
    if (data.comparison_period) {
      series.push({
        name: `${item.series_name} 上一周期${metric.name}`,
        type: chartType,
        data: baselineValues,
        itemStyle: {
          color: chartComparisonPalette[index % chartComparisonPalette.length],
          opacity: 0.52,
        },
        ...(chartType === 'line'
          ? {
              connectNulls: false,
              symbol: 'none',
              lineStyle: {
                color: chartComparisonPalette[index % chartComparisonPalette.length],
                type: 'dashed',
                width: 1.5,
              },
            }
          : {}),
      })
    }
  })

  return {
    color: COLORS,
    animationDuration: 250,
    aria: {
      enabled: true,
      description: `${metric.name}24小时真实值，当前周期${data.current_period.start}至${data.current_period.end}`,
    },
    legend: { top: 4, type: 'scroll' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, confine: true },
    toolbox: {
      right: 8,
      feature: {
        dataZoom: {},
        restore: {},
        saveAsImage: {
          name: `${metric.name}_${data.current_period.start}_${data.current_period.end}`,
          backgroundColor: chartSemanticColors.canvas,
        },
      },
    },
    grid: { left: 82, right: 32, top: 62, bottom: 74 },
    xAxis: {
      type: 'category',
      data: hours,
      boundaryGap: chartType !== 'line',
      axisLabel: { interval: 0, rotate: 45, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: `${metric.name}（${metric.unit}）`,
      scale: true,
      splitLine: { lineStyle: { color: chartSemanticColors.grid, type: 'dashed' } },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 18, bottom: 4, start: 0, end: 100 },
    ],
    media: [
      {
        query: { maxWidth: 480 },
        option: {
          legend: { top: 4, left: 8, right: 8, type: 'scroll' },
          toolbox: { top: 36, right: 8 },
          grid: { left: 52, right: 18, top: 86, bottom: 76 },
          xAxis: {
            axisLabel: { interval: 2, rotate: 45, fontSize: 10, hideOverlap: true },
          },
        },
      },
    ],
    series,
  }
}
