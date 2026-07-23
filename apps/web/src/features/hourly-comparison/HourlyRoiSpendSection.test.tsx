import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, vi } from 'vitest'
import type { DashboardFilters, FilterOptions } from '@/types/dashboard'
import type {
  HourPeriodValues,
  HourlyComparisonResponse,
  HourlySeriesPoint,
} from '@/types/hourlyComparison'

const apiMocks = vi.hoisted(() => ({
  getHourlyComparison: vi.fn(),
  getHourlyComparisonDetails: vi.fn(),
  downloadHourlyComparison: vi.fn(),
}))

vi.mock('@/api/client', () => apiMocks)
vi.mock('@/components/ECharts', () => ({
  ECharts: ({
    option,
    onEvents,
  }: {
    option: { series?: Array<{ type?: string }> }
    onEvents?: { click?: (event: { dataIndex: number }) => void }
  }) => (
    <button
      type="button"
      data-testid="hourly-chart"
      data-has-candlestick={String(option.series?.some((item) => item.type === 'candlestick'))}
      onClick={() => onEvents?.click?.({ dataIndex: 8 })}
    >
      模拟联动图表
    </button>
  ),
}))

import { HourlyRoiSpendSection } from './HourlyRoiSpendSection'

afterEach(async () => {
  // Ant Design/React may leave scheduler work queued after RTL unmounts the
  // portal-heavy section. Drain that queue before jsdom removes `window`.
  await act(async () => {
    await new Promise<void>((resolve) => setImmediate(resolve))
  })
})

const emptyValues = (): HourPeriodValues => ({
  roi: null,
  spend: null,
  metrics: {},
  roi_ohlc: null,
  spend_ohlc: null,
  metric_ohlc: {},
  effective_days: 0,
  effective_samples: 0,
  expected_samples: null,
  coverage_rate: null,
  in_progress: false,
  future: false,
})

function comparisonPoint(hour: number): HourlySeriesPoint {
  const key = `${String(hour).padStart(2, '0')}-${String(hour + 1).padStart(2, '0')}`
  const values = emptyValues()
  if (hour === 8) {
    values.roi = 1.9
    values.spend = 13_000
    values.effective_days = 7
    values.effective_samples = 7
    values.expected_samples = 7
    values.coverage_rate = 1
    values.metrics.period_viewers = 12_345
    values.roi_ohlc = {
      open: 1.65,
      close: 1.9,
      high: 2.05,
      low: 1.51,
      average: 1.8,
      median: 1.82,
      total: 12.6,
      effective_days: 7,
      first_date: '2026-07-09',
      last_date: '2026-07-15',
      high_date: '2026-07-12',
      low_date: '2026-07-09',
    }
    values.spend_ohlc = { ...values.roi_ohlc, open: 9_500, close: 13_000, high: 14_200, low: 9_100 }
    values.metric_ohlc.period_viewers = {
      ...values.roi_ohlc,
      open: 10_200,
      close: 12_345,
      high: 13_000,
      low: 9_800,
    }
  }
  return {
    hour: key,
    label: `${String(hour).padStart(2, '0')}:00-${String(hour + 1).padStart(2, '0')}:00`,
    sort: hour,
    current: values,
    comparison:
      hour === 8
        ? {
            ...emptyValues(),
            roi: 1.4,
            spend: 10_000,
            metrics: { period_viewers: 10_000 },
          }
        : emptyValues(),
    comparison_result: {
      roi_difference: hour === 8 ? 0.5 : null,
      roi_ratio: hour === 8 ? 1.3571 : null,
      roi_percentage: hour === 8 ? 135.71 : null,
      roi_growth: hour === 8 ? 0.3571 : null,
      roi_growth_percentage: hour === 8 ? 35.71 : null,
      spend_difference: hour === 8 ? 3_000 : null,
      spend_ratio: hour === 8 ? 1.3 : null,
      spend_percentage: hour === 8 ? 130 : null,
      spend_growth: hour === 8 ? 0.3 : null,
      spend_growth_percentage: hour === 8 ? 30 : null,
      roi_target_gap: hour === 8 ? 0.09 : null,
      roi_target_attainment: hour === 8 ? 1.0497 : null,
      roi_target_reached: hour === 8 ? true : null,
    },
    roi_target: 1.81,
    target_message: null,
    status: {
      code: hour === 8 ? 'excellent_scaling' : 'no_comparable_baseline',
      name: hour === 8 ? '优秀放量时段' : '无法完整判断',
      level: hour === 8 ? 'positive' : 'neutral',
      reasons: hour === 8 ? ['消耗上涨达到30%', 'ROI上涨达到30%', 'ROI达到目标'] : [],
      reason_codes: [],
      should_push: false,
    },
  }
}

function metricOption(key: string, name: string, unit: string, aggregation = 'SUM') {
  return {
    key,
    name,
    category: '经营',
    unit,
    precision: unit === 'count' ? 0 : 2,
    scope: 'period',
    aggregation,
    numerator: aggregation === 'RATIO_OF_SUMS' ? 'period_overall_amount' : null,
    denominator: aggregation === 'RATIO_OF_SUMS' ? 'period_spend' : null,
    direction: 'higher_is_better',
    default_visible: key !== 'period_viewers',
    supports_hourly_trend: true,
    supports_kline: true,
    supports_alerts: true,
    is_cumulative: false,
  }
}

const response: HourlyComparisonResponse = {
  meta: {
    timezone: 'Asia/Shanghai',
    generated_at: '2026-07-16T12:00:00+08:00',
    data_updated_at: '2026-07-16T11:55:00+08:00',
    period_days: 7,
    aggregation_mode: 'sum',
    chart_type: 'line',
    series_dimension: 'room',
    include_today: false,
    compare_enabled: true,
  },
  current_period: { start: '2026-07-09', end: '2026-07-15', days: 7, complete: true },
  comparison_period: { start: '2026-07-02', end: '2026-07-08', days: 7, complete: true },
  hours: Array.from({ length: 24 }, (_, hour) => ({
    key: comparisonPoint(hour).hour,
    label: comparisonPoint(hour).label,
    sort: hour,
  })),
  metrics: [
    metricOption('period_overall_roi', '时段整体支付ROI', 'ratio', 'RATIO_OF_SUMS'),
    metricOption('period_spend', '时段消耗', 'currency'),
    metricOption('period_viewers', '时段观看人数', 'count'),
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
      points: Array.from({ length: 24 }, (_, hour) => comparisonPoint(hour)),
    },
  ],
}

const dashboardFilters: DashboardFilters = {
  startDate: '2026-07-09',
  endDate: '2026-07-15',
  dateMode: 'day',
  roomIds: ['room-1'],
  anchors: [],
  anchorMembers: [],
  controls: [],
  hours: [],
  metricKeys: [],
  grain: 'hour',
}

const options: FilterOptions = {
  min_date: '2026-07-01',
  max_date: '2026-07-15',
  months: ['2026-07'],
  rooms: [{ id: 'room-1', name: '柏瑞美-散粉' }],
  anchors: [],
  anchor_members: [],
  controls: [],
  hour_slots: [],
  metrics: [],
  comparison_types: [],
}

function LocationProbe() {
  return <output data-testid="location-search">{useLocation().search}</output>
}

function renderSection(
  filters = dashboardFilters,
  entry = '/overview?start=2026-07-09&end=2026-07-15&rooms=room-1',
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <LocationProbe />
        <HourlyRoiSpendSection
          filters={filters}
          options={options}
          onGlobalFiltersChange={vi.fn()}
          focusMetric={null}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('拆分选择器有独立可读宽度契约', async () => {
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  renderSection()

  await screen.findByText('24小时ROI与消耗周期对比')
  const select = screen.getByRole('combobox', { name: '24小时图表拆分方式' })

  expect(select.closest('.ant-select')).toHaveClass('hourly-dimension-select')
})

test('没有本区域覆盖时继承经营总览全局三日周期', async () => {
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  const filters = {
    ...dashboardFilters,
    startDate: '2026-07-13',
    endDate: '2026-07-15',
  }

  renderSection(filters, '/overview?start=2026-07-13&end=2026-07-15&rooms=room-1')

  await waitFor(() =>
    expect(apiMocks.getHourlyComparison).toHaveBeenLastCalledWith(
      expect.objectContaining({
        periodDays: 3,
        endDate: '2026-07-15',
      }),
    ),
  )
})

test('低频显示与导出设置通过渐进展开呈现', async () => {
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  renderSection()

  expect(await screen.findByText('24小时ROI与消耗周期对比')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /导出图片/ })).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: /更多设置与导出/ }))

  expect(screen.getByRole('switch', { name: '周期波动区间' })).toBeInTheDocument()
  expect(screen.getByRole('switch', { name: '全部数据标签' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出图片/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出数据/ })).toBeInTheDocument()
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 100))
  })
})

test('周期/图表切换、24行表和图表点击详情联动', async () => {
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  apiMocks.getHourlyComparisonDetails.mockResolvedValue({
    summary: [response.series[0]!.points[8]!],
    daily_rows: [{ period_type: 'current', date: '2026-07-15', room: '柏瑞美-散粉' }],
    room_rows: [],
    kline_rows: [],
    raw_records: [],
    page: 1,
    page_size: 50,
    raw_total: 0,
  })
  renderSection()

  expect(await screen.findByText('24小时ROI与消耗周期对比')).toBeInTheDocument()
  expect(await screen.findByText('ROI目标 1.81')).toBeInTheDocument()
  expect(await screen.findByText('00-01')).toBeInTheDocument()
  expect(screen.getByText('23-24')).toBeInTheDocument()

  fireEvent.click(screen.getByText('3天'))
  await waitFor(() =>
    expect(apiMocks.getHourlyComparison).toHaveBeenLastCalledWith(
      expect.objectContaining({ periodDays: 3 }),
    ),
  )

  fireEvent.click(screen.getByText('业务K线'))
  await waitFor(() =>
    expect(screen.getByTestId('hourly-chart')).toHaveAttribute('data-has-candlestick', 'true'),
  )

  fireEvent.click(screen.getByTestId('hourly-chart'))
  expect(await screen.findByText('08:00-09:00 分时详情')).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: '08:00-09:00 时段表现' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '核心表现' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '明细数据' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /查看原小时趋势/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /查看相关预警/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出 CSV/ })).toBeInTheDocument()
  expect(apiMocks.getHourlyComparisonDetails).toHaveBeenCalledWith(
    expect.objectContaining({ roomIds: ['room-1'] }),
    '08-09',
    1,
  )
  expect((await screen.findAllByText('2026-07-15')).length).toBeGreaterThan(0)
})

test('选择附加指标后显示真实当前/基准值并发送筛选参数', async () => {
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  renderSection()
  await screen.findByText('24小时ROI与消耗周期对比')

  fireEvent.mouseDown(screen.getByLabelText('24小时指标'))
  fireEvent.click(await screen.findByText('时段观看人数'))

  await waitFor(() =>
    expect(apiMocks.getHourlyComparison).toHaveBeenLastCalledWith(
      expect.objectContaining({
        metricIds: ['period_overall_roi', 'period_spend', 'period_viewers'],
      }),
    ),
  )
  expect(await screen.findByText('已选附加指标 · 柏瑞美-散粉')).toBeInTheDocument()
  expect(screen.getAllByText('时段观看人数（当前）').length).toBeGreaterThan(0)
  expect(screen.getAllByText('时段观看人数（基准）').length).toBeGreaterThan(0)
  expect(screen.getByText('12,345')).toBeInTheDocument()
  expect(screen.getByText('10,000')).toBeInTheDocument()
  expect(screen.getAllByTestId('hourly-chart')).toHaveLength(2)
})

test('接口失败只显示局部错误并可重试', async () => {
  apiMocks.getHourlyComparison.mockRejectedValueOnce(new Error('network'))
  renderSection()
  expect(await screen.findByText('24小时周期对比加载失败')).toBeInTheDocument()
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  fireEvent.click(screen.getByRole('button', { name: '重试24小时数据' }))
  expect(await screen.findByText('ROI目标 1.81')).toBeInTheDocument()
})

test('开启波动区间时原子保留日均口径与波动参数', async () => {
  apiMocks.getHourlyComparison.mockResolvedValue(response)
  renderSection()
  await screen.findByText('24小时ROI与消耗周期对比')

  fireEvent.click(screen.getByRole('button', { name: /更多设置与导出/ }))
  fireEvent.click(screen.getByRole('switch', { name: '周期波动区间' }))

  await waitFor(() => {
    const search = new URLSearchParams(
      screen.getByTestId('location-search').textContent?.replace(/^\?/, ''),
    )
    expect(search.get('hc_aggregation')).toBe('daily_average')
    expect(search.get('hc_range')).toBe('1')
  })
  await waitFor(() =>
    expect(apiMocks.getHourlyComparison).toHaveBeenLastCalledWith(
      expect.objectContaining({ aggregationMode: 'daily_average', showRangeBand: true }),
    ),
  )
})
