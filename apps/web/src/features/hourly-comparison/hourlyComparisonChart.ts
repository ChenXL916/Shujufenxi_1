import type { EChartsCoreOption as EChartsOption } from 'echarts/core'
import type { BarSeriesOption, CandlestickSeriesOption, LineSeriesOption } from 'echarts/charts'
import type {
  BusinessKlinePayload,
  HourlyChartType,
  HourlyComparisonResponse,
  HourlyComparisonSeries,
  NumericValue,
} from '@/types/hourlyComparison'
import {
  chartComparisonPalette,
  chartPalette,
  chartSemanticColors,
  chartStatusColors,
} from '@/theme/chartTheme'
import { createLinePointHitTarget } from '@/utils/chartHitTarget'

type ChartSeries = BarSeriesOption | CandlestickSeriesOption | LineSeriesOption

const COLORS = chartPalette
const STATUS_COLORS: Record<string, string> = chartStatusColors

function numberOrNull(value: NumericValue): number | null {
  if (value === null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function candleValue(value: BusinessKlinePayload | null): [number, number, number, number] {
  if (!value) return [Number.NaN, Number.NaN, Number.NaN, Number.NaN]
  const values = [value.open, value.close, value.low, value.high].map(numberOrNull)
  if (values.some((item) => item === null)) {
    return [Number.NaN, Number.NaN, Number.NaN, Number.NaN]
  }
  return values as [number, number, number, number]
}

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ??
      character,
  )
}

function display(value: NumericValue, precision = 2): string {
  const numeric = numberOrNull(value)
  return numeric === null
    ? '—'
    : numeric.toLocaleString('zh-CN', { maximumFractionDigits: precision })
}

function percentage(value: NumericValue): string {
  const numeric = numberOrNull(value)
  return numeric === null ? '—' : `${numeric.toFixed(2)}%`
}

export function formatHourlyLegendLabel(name: string): string {
  const normalized = name.replace(/^全部直播间\s+/, '')
  const matched = normalized.match(/^(.*?)(?:\s+)?(当前|上一周期)(ROI|消耗)$/)
  if (!matched) return normalized
  const [, entity, period, metric] = matched
  const periodLabel = period === '上一周期' ? '上周期' : '当前'
  return entity ? `${entity} · ${periodLabel} ${metric}` : `${periodLabel} · ${metric}`
}

export function formatComparisonNarrative(current: NumericValue, baseline: NumericValue): string {
  const currentNumber = numberOrNull(current)
  const baselineNumber = numberOrNull(baseline)
  if (currentNumber === null || baselineNumber === null || baselineNumber === 0) {
    return '无有效可比基准'
  }
  const ratio = (currentNumber / baselineNumber) * 100
  const growth = ((currentNumber - baselineNumber) / baselineNumber) * 100
  const verb = growth >= 0 ? '提升' : '下降'
  return `当前是基准的${ratio.toFixed(2)}%，较基准${verb}${Math.abs(growth).toFixed(2)}%`
}

function statusPoints(series: HourlyComparisonSeries, metric: 'roi' | 'spend') {
  return series.points.flatMap((point) => {
    const value = numberOrNull(point.current[metric])
    if (['normal', 'neutral'].includes(point.status.level) || value === null) return []
    return [
      {
        name: point.status.name,
        coord: [point.hour, value] as [string, number],
        itemStyle: { color: STATUS_COLORS[point.status.level] ?? chartSemanticColors.muted },
        label: { formatter: point.status.name },
      },
    ]
  })
}

function selectedPoint(
  series: HourlyComparisonSeries,
  metric: 'roi' | 'spend',
  selectedHour: string | null,
  color: string,
) {
  if (!selectedHour) return []
  const point = series.points.find((item) => item.hour === selectedHour)
  const value = numberOrNull(point?.current[metric] ?? null)
  if (value === null) return []
  return [
    {
      name: '当前选中小时',
      coord: [selectedHour, value] as [string, number],
      symbol: 'circle',
      symbolSize: 24,
      itemStyle: {
        color: '#FFFFFF',
        borderColor: color,
        borderWidth: 3,
        shadowBlur: 12,
        shadowColor: 'rgba(23, 23, 22, 0.18)',
      },
      label: { show: false },
      tooltip: { show: false },
    },
  ]
}

function selectedLine(selectedHour: string | null): Array<Record<string, unknown>> {
  return selectedHour
    ? [
        {
          name: '当前选中小时',
          xAxis: selectedHour,
          lineStyle: { color: chartSemanticColors.muted, type: 'dotted', width: 1 },
          label: { formatter: selectedHour },
        },
      ]
    : []
}

function targetAndSelectedLines(
  series: HourlyComparisonSeries,
  selectedHour: string | null,
): Array<Record<string, unknown>> {
  const target = numberOrNull(series.roi_target)
  return [
    ...(target === null
      ? []
      : [
          {
            name: `ROI目标 ${target.toFixed(2)}`,
            yAxis: target,
            lineStyle: { color: chartSemanticColors.target, type: 'dashed', width: 1.5 },
            label: { formatter: `ROI目标 ${target.toFixed(2)}` },
          },
        ]),
    ...selectedLine(selectedHour),
  ]
}

function currentLine(
  series: HourlyComparisonSeries,
  metric: 'roi' | 'spend',
  index: number,
  selectedHour: string | null,
  showAllLabels: boolean,
): LineSeriesOption {
  const metricLabel = metric === 'roi' ? 'ROI' : '消耗'
  const color = COLORS[index % COLORS.length] ?? chartSemanticColors.current
  return {
    name: `${series.series_name} 当前${metricLabel}`,
    type: 'line',
    xAxisIndex: metric === 'roi' ? 0 : 1,
    yAxisIndex: metric === 'roi' ? 0 : 1,
    data: series.points.map((point) => numberOrNull(point.current[metric])),
    connectNulls: false,
    smooth: false,
    showSymbol: true,
    symbolSize: 8,
    z: 6,
    lineStyle: { color, width: 2.4, type: 'solid' },
    itemStyle: { color, borderColor: '#FFFFFF', borderWidth: 1.5 },
    emphasis: {
      focus: 'series',
      scale: true,
      lineStyle: { width: 3.2, opacity: 1 },
      itemStyle: {
        borderColor: '#FFFFFF',
        borderWidth: 2,
        shadowBlur: 10,
        shadowColor: 'rgba(23, 23, 22, 0.22)',
      },
    },
    blur: {
      lineStyle: { opacity: 0.2 },
      itemStyle: { opacity: 0.28 },
    },
    label: {
      show: showAllLabels,
      position: 'top',
      formatter: ({ value }: { value?: unknown }) =>
        typeof value === 'number' ? display(value) : '',
    },
    markLine: {
      silent: true,
      symbol: ['none', 'none'],
      data:
        metric === 'roi'
          ? targetAndSelectedLines(series, selectedHour)
          : selectedLine(selectedHour),
    },
    markPoint: {
      symbolSize: 38,
      data: [
        ...statusPoints(series, metric),
        ...selectedPoint(series, metric, selectedHour, color),
      ],
      label: { color: chartSemanticColors.onStatus, fontSize: 10 },
    },
  }
}

function comparisonLine(
  series: HourlyComparisonSeries,
  metric: 'roi' | 'spend',
  index: number,
): LineSeriesOption {
  const metricLabel = metric === 'roi' ? 'ROI' : '消耗'
  const color =
    chartComparisonPalette[index % chartComparisonPalette.length] ?? chartSemanticColors.comparison
  return {
    name: `${series.series_name} 上一周期${metricLabel}`,
    type: 'line',
    xAxisIndex: metric === 'roi' ? 0 : 1,
    yAxisIndex: metric === 'roi' ? 0 : 1,
    data: series.points.map((point) => numberOrNull(point.comparison?.[metric] ?? null)),
    connectNulls: false,
    smooth: false,
    showSymbol: false,
    z: 4,
    lineStyle: {
      color,
      width: 1.8,
      type: 'dashed',
      opacity: 0.76,
    },
    itemStyle: {
      color,
      opacity: 0.76,
    },
    emphasis: {
      focus: 'series',
      lineStyle: { width: 2.8, opacity: 1 },
      itemStyle: {
        color,
        opacity: 1,
        borderColor: '#FFFFFF',
        borderWidth: 2,
        shadowBlur: 8,
        shadowColor: 'rgba(23, 23, 22, 0.16)',
      },
    },
    blur: {
      lineStyle: { opacity: 0.18 },
      itemStyle: { opacity: 0.22 },
    },
  }
}

function lineHitTargets(
  series: HourlyComparisonSeries,
  index: number,
  comparison: boolean,
): LineSeriesOption[] {
  const period = comparison ? 'comparison' : 'current'
  const color = comparison
    ? chartComparisonPalette[index % chartComparisonPalette.length]
    : COLORS[index % COLORS.length]
  return (['roi', 'spend'] as const).map((metric) => {
    const metricLabel = metric === 'roi' ? 'ROI' : '消耗'
    return createLinePointHitTarget({
      id: `hourly-hit-${index}-${period}-${metric}`,
      name: `${series.series_name} ${comparison ? '上一周期' : '当前'}${metricLabel}`,
      data: series.points.map((point) =>
        numberOrNull(comparison ? (point.comparison?.[metric] ?? null) : point.current[metric]),
      ),
      color: color ?? COLORS[0] ?? '#1677ff',
      xAxisIndex: metric === 'roi' ? 0 : 1,
      yAxisIndex: metric === 'roi' ? 0 : 1,
    })
  })
}

function rangeBand(
  series: HourlyComparisonSeries,
  metric: 'roi' | 'spend',
  index: number,
): LineSeriesOption[] {
  const isRoi = metric === 'roi'
  const ohlcKey = isRoi ? 'roi_ohlc' : 'spend_ohlc'
  const lows = series.points.map((point) => numberOrNull(point.current[ohlcKey]?.low ?? null))
  const spans = series.points.map((point, pointIndex) => {
    const low = lows[pointIndex] ?? null
    const high = numberOrNull(point.current[ohlcKey]?.high ?? null)
    return low === null || high === null ? null : high - low
  })
  const stack = `range-${metric}-${index}`
  const axes = isRoi ? { xAxisIndex: 0, yAxisIndex: 0 } : { xAxisIndex: 1, yAxisIndex: 1 }
  return [
    {
      name: `${series.series_name} ${isRoi ? 'ROI' : '消耗'}区间下界`,
      type: 'line',
      ...axes,
      data: lows,
      stack,
      connectNulls: false,
      showSymbol: false,
      silent: true,
      lineStyle: { opacity: 0 },
      areaStyle: { opacity: 0 },
      tooltip: { show: false },
    },
    {
      name: `${series.series_name} ${isRoi ? 'ROI' : '消耗'}日波动区间`,
      type: 'line',
      ...axes,
      data: spans,
      stack,
      connectNulls: false,
      showSymbol: false,
      silent: true,
      lineStyle: { opacity: 0 },
      areaStyle: { color: COLORS[index % COLORS.length], opacity: 0.12 },
      tooltip: { show: false },
    },
  ]
}

function barSeries(
  series: HourlyComparisonSeries,
  metric: 'roi' | 'spend',
  index: number,
  comparison: boolean,
): BarSeriesOption {
  const metricLabel = metric === 'roi' ? 'ROI' : '消耗'
  return {
    name: `${series.series_name} ${comparison ? '上一周期' : '当前'}${metricLabel}`,
    type: 'bar',
    xAxisIndex: metric === 'roi' ? 0 : 1,
    yAxisIndex: metric === 'roi' ? 0 : 1,
    data: series.points.map((point) =>
      numberOrNull(comparison ? (point.comparison?.[metric] ?? null) : point.current[metric]),
    ),
    itemStyle: {
      color: comparison
        ? chartComparisonPalette[index % chartComparisonPalette.length]
        : COLORS[index % COLORS.length],
      opacity: comparison ? 0.42 : 0.9,
      borderType: comparison ? 'dashed' : 'solid',
    },
    barGap: comparison ? '-35%' : '20%',
  }
}

function businessKlineSeries(
  series: HourlyComparisonSeries,
  metric: 'roi' | 'spend',
  selectedHour: string | null,
): ChartSeries[] {
  const isRoi = metric === 'roi'
  const label = isRoi ? 'ROI' : '消耗'
  const current: CandlestickSeriesOption = {
    name: `${series.series_name} ${label}业务K线`,
    type: 'candlestick',
    xAxisIndex: isRoi ? 0 : 1,
    yAxisIndex: isRoi ? 0 : 1,
    data: series.points.map((point) =>
      candleValue(isRoi ? point.current.roi_ohlc : point.current.spend_ohlc),
    ),
    itemStyle: isRoi
      ? {
          color: chartSemanticColors.positive,
          color0: chartSemanticColors.negative,
          borderColor: chartSemanticColors.positive,
          borderColor0: chartSemanticColors.negative,
        }
      : {
          color: chartSemanticColors.comparison,
          color0: chartSemanticColors.current,
          borderColor: chartSemanticColors.comparison,
          borderColor0: chartSemanticColors.current,
        },
    markLine: {
      silent: true,
      symbol: ['none', 'none'],
      data: isRoi ? targetAndSelectedLines(series, selectedHour) : selectedLine(selectedHour),
    },
  }
  const comparisonClose: LineSeriesOption = {
    name: `${series.series_name} 上一周期${label} close`,
    type: 'line',
    xAxisIndex: isRoi ? 0 : 1,
    yAxisIndex: isRoi ? 0 : 1,
    data: series.points.map((point) =>
      numberOrNull(
        isRoi
          ? (point.comparison?.roi_ohlc?.close ?? null)
          : (point.comparison?.spend_ohlc?.close ?? null),
      ),
    ),
    connectNulls: false,
    showSymbol: false,
    lineStyle: { color: chartSemanticColors.comparison, type: 'dashed', width: 1.5 },
  }
  return [current, comparisonClose]
}

function selectedSeries(payload: HourlyComparisonResponse, activeSeriesKey: string | null) {
  return payload.series.find((item) => item.series_key === activeSeriesKey) ?? payload.series[0]
}

function tooltip(
  payload: HourlyComparisonResponse,
  chartParameters: unknown,
  activeSeriesKey: string | null,
): string {
  const parameters: unknown[] = Array.isArray(chartParameters)
    ? (chartParameters as unknown[])
    : [chartParameters]
  const candidate: unknown = parameters[0]
  const dataIndex =
    candidate && typeof candidate === 'object' && 'dataIndex' in candidate
      ? Number(candidate.dataIndex)
      : -1
  const series = selectedSeries(payload, activeSeriesKey)
  const point = series?.points[dataIndex]
  if (!series || !point) return ''
  const comparisonRange = payload.comparison_period
    ? `${payload.comparison_period.start} 至 ${payload.comparison_period.end}`
    : '已关闭'
  const reasons = point.status.reasons.length
    ? point.status.reasons.map(escapeHtml).join('；')
    : '暂无'
  return [
    `<strong>${escapeHtml(point.label)}｜${escapeHtml(series.series_name)}</strong>`,
    `当前周期：${payload.current_period.start} 至 ${payload.current_period.end}`,
    `对比周期：${comparisonRange}`,
    `当前ROI：${display(point.current.roi)}；基准ROI：${display(point.comparison?.roi ?? null)}`,
    `ROI涨幅：${percentage(point.comparison_result.roi_growth_percentage)}`,
    `当前消耗：¥${display(point.current.spend)}；基准消耗：¥${display(point.comparison?.spend ?? null)}`,
    `消耗涨幅：${percentage(point.comparison_result.spend_growth_percentage)}`,
    `ROI目标：${display(point.roi_target)}；目标差：${display(point.comparison_result.roi_target_gap)}`,
    `有效样本：${point.current.effective_samples}/${point.current.expected_samples ?? '暂无排班基准'}`,
    `覆盖率：${percentage(
      numberOrNull(point.current.coverage_rate) === null
        ? null
        : Number(point.current.coverage_rate) * 100,
    )}`,
    `综合状态：${escapeHtml(point.status.name)}`,
    `原因：${reasons}`,
    `飞书推送：${point.status.should_push ? '会触发' : '不会触发'}`,
  ].join('<br/>')
}

export function buildHourlyChartOption(
  payload: HourlyComparisonResponse,
  chartType: HourlyChartType,
  selectedHour: string | null,
  showAllLabels: boolean,
  showRangeBand = false,
  activeSeriesKey: string | null = null,
): EChartsOption {
  const hours = payload.hours.map((item) => item.key)
  const series: ChartSeries[] = []
  if (chartType === 'business_kline') {
    const active = selectedSeries(payload, activeSeriesKey)
    if (active) {
      series.push(...businessKlineSeries(active, 'roi', selectedHour))
      series.push(...businessKlineSeries(active, 'spend', selectedHour))
    }
  } else {
    payload.series.slice(0, 6).forEach((item, index) => {
      if (chartType === 'bar') {
        series.push(barSeries(item, 'roi', index, false), barSeries(item, 'spend', index, false))
        if (payload.comparison_period) {
          series.push(barSeries(item, 'roi', index, true), barSeries(item, 'spend', index, true))
        }
      } else {
        if (showRangeBand) {
          series.push(...rangeBand(item, 'roi', index), ...rangeBand(item, 'spend', index))
        }
        series.push(currentLine(item, 'roi', index, selectedHour, showAllLabels))
        series.push(currentLine(item, 'spend', index, selectedHour, showAllLabels))
        series.push(...lineHitTargets(item, index, false))
        if (payload.comparison_period) {
          series.push(comparisonLine(item, 'roi', index), comparisonLine(item, 'spend', index))
          series.push(...lineHitTargets(item, index, true))
        }
      }
    })
  }
  return {
    color: COLORS,
    animationDuration: 250,
    aria: {
      enabled: true,
      description: `24小时ROI与消耗周期对比，当前周期${payload.current_period.start}至${payload.current_period.end}`,
    },
    legend: {
      top: 4,
      left: 8,
      right: 8,
      type: 'scroll',
      icon: 'roundRect',
      itemWidth: 22,
      itemHeight: 5,
      itemGap: 18,
      formatter: formatHourlyLegendLabel,
      selectedMode: true,
      inactiveColor: '#C4BFB6',
      textStyle: {
        color: '#4F4B45',
        fontSize: 11,
        fontWeight: 560,
      },
      tooltip: { show: true },
    },
    toolbox: {
      top: 34,
      right: 8,
      feature: {
        dataZoom: {},
        restore: {},
        saveAsImage: {
          name: `24小时ROI消耗对比_${payload.current_period.start}_${payload.current_period.end}`,
          backgroundColor: chartSemanticColors.canvas,
        },
      },
    },
    tooltip: {
      trigger: 'axis',
      transitionDuration: 0.12,
      axisPointer: {
        type: 'cross',
        snap: true,
        lineStyle: { color: 'rgba(196, 71, 32, 0.5)', width: 1 },
        crossStyle: { color: 'rgba(196, 71, 32, 0.5)', width: 1 },
        label: {
          color: '#FFFFFF',
          backgroundColor: '#2B2926',
          borderRadius: 6,
          padding: [4, 7],
        },
      },
      confine: true,
      formatter: (parameters: unknown) => tooltip(payload, parameters, activeSeriesKey),
    },
    axisPointer: {
      link: [{ xAxisIndex: [0, 1] }],
      lineStyle: { color: 'rgba(196, 71, 32, 0.5)', width: 1 },
      label: {
        color: '#FFFFFF',
        backgroundColor: '#2B2926',
        borderRadius: 6,
        padding: [4, 7],
      },
    },
    grid: [
      { left: 72, right: 30, top: 68, height: '31%' },
      { left: 72, right: 30, top: '55%', height: '31%' },
    ],
    xAxis: [
      {
        type: 'category',
        gridIndex: 0,
        data: hours,
        boundaryGap: chartType !== 'line',
        axisLabel: { interval: 0, rotate: 45, fontSize: 11 },
        axisPointer: { show: true, snap: true },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: hours,
        boundaryGap: chartType !== 'line',
        axisLabel: { interval: 0, rotate: 45, fontSize: 11 },
        axisPointer: { show: true, snap: true },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        name: 'ROI',
        scale: true,
        splitLine: { lineStyle: { color: chartSemanticColors.grid, type: 'dashed' } },
      },
      {
        type: 'value',
        gridIndex: 1,
        name: '消耗（元）',
        scale: true,
        splitLine: { lineStyle: { color: chartSemanticColors.grid, type: 'dashed' } },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1], height: 18, bottom: 12, start: 0, end: 100 },
    ],
    media: [
      {
        query: { maxWidth: 480 },
        option: {
          legend: { top: 4, left: 8, right: 8, type: 'scroll' },
          toolbox: { top: 36, right: 8 },
          grid: [
            { left: 50, right: 18, top: 88, height: '28%' },
            { left: 50, right: 18, top: '57%', height: '27%' },
          ],
          xAxis: [
            { axisLabel: { interval: 2, rotate: 45, fontSize: 10, hideOverlap: true } },
            { axisLabel: { interval: 2, rotate: 45, fontSize: 10, hideOverlap: true } },
          ],
          dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
            {
              type: 'slider',
              xAxisIndex: [0, 1],
              height: 16,
              bottom: 10,
              start: 0,
              end: 100,
            },
          ],
        },
      },
    ],
    series,
  }
}
