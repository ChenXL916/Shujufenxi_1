import type { EChartsCoreOption as EChartsOption } from 'echarts/core'
import { describe, expect, test } from 'vitest'
import type { HourlyComparisonResponse, HourlySeriesPoint } from '@/types/hourlyComparison'
import {
  buildHourlyChartOption,
  formatComparisonNarrative,
  formatHourlyLegendLabel,
} from './hourlyComparisonChart'
import { buildAdditionalMetricOption } from './additionalMetricChartOption'

function point(hour: number): HourlySeriesPoint {
  const key = `${String(hour).padStart(2, '0')}-${String(hour + 1).padStart(2, '0')}`
  const hasValue = hour === 8
  const kline = hasValue
    ? {
        open: 1.65,
        close: 1.9,
        high: 2.05,
        low: 1.5,
        average: 1.8,
        median: 1.85,
        total: 5.4,
        effective_days: 3,
        first_date: '2026-07-13',
        last_date: '2026-07-15',
        high_date: '2026-07-14',
        low_date: '2026-07-13',
      }
    : null
  return {
    hour: key,
    label: `${String(hour).padStart(2, '0')}:00-${String(hour + 1).padStart(2, '0')}:00`,
    sort: hour,
    current: {
      roi: hasValue ? 1.9 : null,
      spend: hasValue ? 13_000 : null,
      metrics: { period_viewers: hasValue ? 12_345 : null },
      roi_ohlc: kline,
      spend_ohlc: kline ? { ...kline, open: 9_500, close: 13_000, high: 14_200, low: 9_100 } : null,
      metric_ohlc: {
        period_viewers: kline
          ? { ...kline, open: 10_200, close: 12_345, high: 13_000, low: 9_800 }
          : null,
      },
      effective_days: hasValue ? 3 : 0,
      effective_samples: hasValue ? 3 : 0,
      expected_samples: hasValue ? 3 : null,
      coverage_rate: hasValue ? 1 : null,
      in_progress: false,
      future: false,
    },
    comparison: {
      roi: hasValue ? 1.4 : null,
      spend: hasValue ? 10_000 : null,
      metrics: { period_viewers: hasValue ? 10_000 : null },
      roi_ohlc: kline ? { ...kline, open: 1.2, close: 1.4, high: 1.5, low: 1.1 } : null,
      spend_ohlc: kline ? { ...kline, open: 8_000, close: 10_000, high: 11_000, low: 7_500 } : null,
      metric_ohlc: {},
      effective_days: hasValue ? 3 : 0,
      effective_samples: hasValue ? 3 : 0,
      expected_samples: hasValue ? 3 : null,
      coverage_rate: hasValue ? 1 : null,
      in_progress: false,
      future: false,
    },
    comparison_result: {
      roi_difference: hasValue ? 0.5 : null,
      roi_ratio: hasValue ? 1.3571 : null,
      roi_percentage: hasValue ? 135.71 : null,
      roi_growth: hasValue ? 0.3571 : null,
      roi_growth_percentage: hasValue ? 35.71 : null,
      spend_difference: hasValue ? 3_000 : null,
      spend_ratio: hasValue ? 1.3 : null,
      spend_percentage: hasValue ? 130 : null,
      spend_growth: hasValue ? 0.3 : null,
      spend_growth_percentage: hasValue ? 30 : null,
      roi_target_gap: hasValue ? 0.09 : null,
      roi_target_attainment: hasValue ? 1.0497 : null,
      roi_target_reached: hasValue ? true : null,
    },
    roi_target: 1.81,
    target_message: null,
    status: {
      code: hasValue ? 'excellent_scaling' : 'no_comparable_baseline',
      name: hasValue ? '优秀放量时段' : '无法完整判断',
      level: hasValue ? 'positive' : 'neutral',
      reasons: hasValue ? ['消耗上涨达到30%', 'ROI上涨达到30%', 'ROI达到目标'] : [],
      reason_codes: [],
      should_push: false,
    },
  }
}

const payload: HourlyComparisonResponse = {
  meta: {
    timezone: 'Asia/Shanghai',
    generated_at: '2026-07-16T12:00:00+08:00',
    data_updated_at: '2026-07-16T11:55:00+08:00',
    period_days: 3,
    aggregation_mode: 'sum',
    chart_type: 'line',
    series_dimension: 'room',
    include_today: false,
    compare_enabled: true,
  },
  current_period: { start: '2026-07-13', end: '2026-07-15', days: 3, complete: true },
  comparison_period: { start: '2026-07-10', end: '2026-07-12', days: 3, complete: true },
  hours: Array.from({ length: 24 }, (_, hour) => ({
    key: point(hour).hour,
    label: point(hour).label,
    sort: hour,
  })),
  metrics: [
    {
      key: 'period_viewers',
      name: '时段观看人数',
      category: '流量',
      unit: 'count',
      precision: 0,
      scope: 'period',
      aggregation: 'SUM',
      numerator: null,
      denominator: null,
      direction: 'higher_is_better',
      default_visible: false,
      supports_hourly_trend: true,
      supports_kline: true,
      supports_alerts: false,
      is_cumulative: false,
    },
  ],
  series: [
    {
      series_key: 'room-1',
      series_name: '柏瑞美-散粉',
      dimension: 'room',
      room_id: 'room-1',
      room_name: '柏瑞美-散粉',
      anchor_name: null,
      product_category: '散粉',
      roi_target: 1.81,
      multiple_targets: false,
      target_message: null,
      points: Array.from({ length: 24 }, (_, hour) => point(hour)),
    },
  ],
}

function seriesList(option: EChartsOption): Array<Record<string, unknown>> {
  return option.series as Array<Record<string, unknown>>
}

describe('24小时图表 option', () => {
  test('折线模式固定24小时、缺失不连线并显示实虚线与目标线', () => {
    const option = buildHourlyChartOption(payload, 'line', '08-09', false)
    expect(option.legend).toEqual(expect.objectContaining({ type: 'scroll', left: 8, right: 8 }))
    expect(option.legend).toEqual(
      expect.objectContaining({
        icon: 'roundRect',
        itemWidth: 22,
        itemHeight: 5,
        selectedMode: true,
      }),
    )
    expect(option.toolbox).toEqual(expect.objectContaining({ top: 34, right: 8 }))
    const slider = (option.dataZoom as Array<Record<string, unknown>>).find(
      (item) => item.type === 'slider',
    )
    expect(slider).toEqual(expect.objectContaining({ bottom: 12 }))
    const xAxes = option.xAxis as Array<{ data: string[] }>
    expect(xAxes).toHaveLength(2)
    expect(xAxes[0]?.data).toHaveLength(24)
    expect(xAxes[0]?.data[0]).toBe('00-01')
    expect(xAxes[0]?.data[23]).toBe('23-24')
    const series = seriesList(option)
    const lines = series.filter((item) => item.type === 'line')
    expect(lines.every((item) => item.connectNulls === false)).toBe(true)
    expect(lines.some((item) => (item.lineStyle as { type?: string }).type === 'dashed')).toBe(true)
    const hitTargets = series.filter((item) => String(item.id).startsWith('hourly-hit-'))
    expect(hitTargets).toHaveLength(4)
    expect(
      hitTargets.every(
        (item) =>
          item.symbolSize === 24 &&
          item.cursor === 'pointer' &&
          (item.tooltip as { show?: boolean }).show === false,
      ),
    ).toBe(true)
    const roiCurrent = series.find((item) => item.name === '柏瑞美-散粉 当前ROI')
    const emphasis = roiCurrent?.emphasis as
      { focus?: string; lineStyle?: { width?: number } } | undefined
    expect(emphasis?.focus).toBe('series')
    expect(emphasis?.lineStyle?.width).toBe(3.2)
    expect(JSON.stringify(roiCurrent?.markLine)).toContain('1.81')
    expect(JSON.stringify(roiCurrent?.markLine)).toContain('08-09')
    const markPoint = roiCurrent?.markPoint as
      { data?: Array<{ name?: string; coord?: [string, number]; symbolSize?: number }> } | undefined
    const selectedMark = markPoint?.data?.find((item) => item.name === '当前选中小时')
    expect(selectedMark?.coord).toEqual(['08-09', 1.9])
    expect(selectedMark?.symbolSize).toBe(24)
    const axisPointer = option.axisPointer as { label?: { backgroundColor?: string } } | undefined
    expect(axisPointer?.label?.backgroundColor).toBe('#2B2926')
    const media = option.media as Array<{
      query?: { maxWidth?: number }
      option?: { toolbox?: { top?: number } }
    }>
    const mobileLayout = media.find((entry) => entry.query?.maxWidth === 480)
    expect(mobileLayout?.option?.toolbox?.top).toBe(36)
  })

  test('业务K线使用真实日小时OHLC且基准用虚线close避免覆盖', () => {
    const option = buildHourlyChartOption(payload, 'business_kline', null, false)
    const series = seriesList(option)
    const roiKline = series.find((item) => item.name === '柏瑞美-散粉 ROI业务K线')
    expect(roiKline?.type).toBe('candlestick')
    const candleData = roiKline?.data as Array<Array<number | string>>
    expect(candleData[8]).toEqual([1.65, 1.9, 1.5, 2.05])
    const comparisonClose = series.find((item) => item.name === '柏瑞美-散粉 上一周期ROI close')
    expect((comparisonClose?.lineStyle as { type?: string }).type).toBe('dashed')
  })

  test('业务K线和提示框跟随当前选中的系列而不是固定第一条', () => {
    const first = payload.series[0]!
    const second = {
      ...first,
      series_key: 'room-2',
      series_name: '第二直播间',
      points: first.points.map((item, index) =>
        index === 8
          ? {
              ...item,
              current: {
                ...item.current,
                roi_ohlc: {
                  ...item.current.roi_ohlc!,
                  open: 2.1,
                  close: 2.4,
                  low: 2,
                  high: 2.5,
                },
              },
            }
          : item,
      ),
    }
    const option = buildHourlyChartOption(
      { ...payload, series: [first, second] },
      'business_kline',
      null,
      false,
      false,
      'room-2',
    )
    const series = seriesList(option)
    const roiKline = series.find((item) => item.name === '第二直播间 ROI业务K线')
    expect(roiKline?.type).toBe('candlestick')
    expect((roiKline?.data as Array<Array<number | string>>)[8]).toEqual([2.1, 2.4, 2, 2.5])

    const formatter = (option.tooltip as { formatter: (value: unknown) => string }).formatter
    expect(formatter([{ dataIndex: 8 }])).toContain('第二直播间')
  })

  test('日均折线波动区间使用daily low/high且缺失保持null', () => {
    const option = buildHourlyChartOption(payload, 'line', null, false, true)
    const series = seriesList(option)
    const roiBand = series.find((item) => item.name === '柏瑞美-散粉 ROI日波动区间')
    const values = roiBand?.data as Array<number | null>
    expect(values[0]).toBeNull()
    expect(values[8]).toBeCloseTo(0.55)
    expect(roiBand?.connectNulls).toBe(false)
  })

  test('附加指标图直接展示API当前/基准数值且缺失不补0', () => {
    const metric = payload.metrics[0]!
    const option = buildAdditionalMetricOption(payload, metric, 'line', null, false)
    const series = seriesList(option)
    const current = series.find((item) => item.name === '柏瑞美-散粉 当前时段观看人数')
    const baseline = series.find((item) => item.name === '柏瑞美-散粉 上一周期时段观看人数')
    expect((current?.data as Array<number | null>)[0]).toBeNull()
    expect((current?.data as Array<number | null>)[8]).toBe(12_345)
    expect((baseline?.data as Array<number | null>)[8]).toBe(10_000)
    expect(current?.connectNulls).toBe(false)
    const hitTargets = series.filter((item) => String(item.id).startsWith('additional-hit-'))
    expect(hitTargets).toHaveLength(2)
    expect(hitTargets.every((item) => item.symbolSize === 24 && item.cursor === 'pointer')).toBe(
      true,
    )
    expect(option.media).toEqual(
      expect.arrayContaining([expect.objectContaining({ query: { maxWidth: 480 } })]),
    )
  })
})

test('对比文案区分当前占比与较基准增幅', () => {
  expect(formatComparisonNarrative(3, 1.5)).toBe('当前是基准的200.00%，较基准提升100.00%')
  expect(formatComparisonNarrative(3, 0)).toBe('无有效可比基准')
})

test('图例压缩汇总前缀并明确当前与上周期', () => {
  expect(formatHourlyLegendLabel('全部直播间 当前ROI')).toBe('当前 · ROI')
  expect(formatHourlyLegendLabel('全部直播间 上一周期消耗')).toBe('上周期 · 消耗')
  expect(formatHourlyLegendLabel('柏瑞美-散粉 当前ROI')).toBe('柏瑞美-散粉 · 当前 ROI')
})
