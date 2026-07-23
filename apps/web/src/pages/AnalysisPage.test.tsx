import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

const analysisOptions = vi.hoisted(() => ({
  min_date: '2026-07-08',
  max_date: '2026-07-08',
  months: ['2026-07'],
  rooms: [{ id: 'room-1', name: '测试直播间' }],
  anchors: ['Q-李昕'],
  anchor_members: ['李昕'],
  controls: ['郑荣贵'],
  hour_slots: ['08-09'],
  metrics: [
    {
      key: 'period_overall_amount',
      name: '时段整体成交金额',
      category: '金额',
      unit: 'currency',
      precision: 2,
      scope: 'period',
      aggregation: 'SUM',
      numerator: null,
      denominator: null,
      direction: 'higher_better',
      default_visible: false,
      analysis_default: true,
      supports_hourly_trend: true,
      supports_kline: true,
      supports_alerts: false,
      is_cumulative: false,
    },
    {
      key: 'period_buyers',
      name: '时段成交人数',
      category: '人数',
      unit: 'count',
      precision: 0,
      scope: 'period',
      aggregation: 'SUM',
      numerator: null,
      denominator: null,
      direction: 'higher_better',
      default_visible: false,
      analysis_default: true,
      supports_hourly_trend: true,
      supports_kline: true,
      supports_alerts: false,
      is_cumulative: false,
    },
    {
      key: 'period_impression_view_rate',
      name: '时段曝光-观看率(人数）',
      category: '转化',
      unit: 'percent',
      precision: 2,
      scope: 'period',
      aggregation: 'NONE',
      numerator: null,
      denominator: null,
      direction: 'higher_better',
      default_visible: false,
      analysis_default: true,
      supports_hourly_trend: false,
      supports_kline: false,
      supports_alerts: false,
      is_cumulative: false,
    },
    {
      key: 'period_spend',
      name: '时段消耗',
      category: '消耗',
      unit: 'currency',
      precision: 2,
      scope: 'period',
      aggregation: 'SUM',
      numerator: null,
      denominator: null,
      direction: 'contextual',
      default_visible: true,
      analysis_default: false,
      supports_hourly_trend: true,
      supports_kline: true,
      supports_alerts: true,
      is_cumulative: false,
    },
  ],
  comparison_types: ['previous_day'],
}))

vi.mock('@/api/client', () => ({
  getFilterOptions: vi.fn().mockResolvedValue(analysisOptions),
  getAnalysis: vi.fn().mockResolvedValue([
    {
      key: 'Q-李昕',
      name: 'Q-李昕',
      valid_hours: 1,
      room_count: 1,
      period_overall_amount: 300,
      period_buyers: 8,
      period_impression_view_rate: 0.25,
    },
  ]),
  getAnchorHourDetails: vi.fn().mockResolvedValue({
    items: [
      {
        key: 'fact-1',
        fact_id: 'fact-1',
        business_date: '2026-07-08',
        hour_slot: '08-09',
        hour_order: 8,
        room_id: 'room-1',
        room_name: '测试直播间',
        anchor_name: 'Q-李昕',
        control_name: '郑荣贵',
        latest_observed_at: '2026-07-08T09:00:00+08:00',
        anchor_match_status: 'matched',
        data_status: 'complete',
        metrics: {
          period_overall_amount: 300,
          period_buyers: 8,
          period_impression_view_rate: 0.25,
        },
      },
    ],
    total: 1,
    page: 1,
    page_size: 50,
    metric_keys: ['period_buyers'],
  }),
}))

import { getAnalysis, getAnchorHourDetails } from '@/api/client'
import { AnalysisPage } from './AnalysisPage'

beforeEach(() => {
  vi.clearAllMocks()
})

test('主播分析未指定指标时只默认勾选配置中的分析指标', async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/anchors?start=2026-07-08&end=2026-07-08']}>
        <AnalysisPage dimension="anchors" />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  expect(await screen.findByText('已选 3 个指标')).toBeInTheDocument()
  expect(await screen.findAllByRole('columnheader', { name: '时段整体成交金额' })).toHaveLength(2)
  expect(await screen.findAllByRole('columnheader', { name: '时段成交人数' })).toHaveLength(2)
  expect(
    screen.getByRole('columnheader', { name: '时段曝光-观看率(人数）（最近时段）' }),
  ).toBeInTheDocument()
  expect(screen.queryByRole('columnheader', { name: '时段消耗' })).not.toBeInTheDocument()
  await waitFor(() =>
    expect(getAnalysis).toHaveBeenCalledWith(
      'anchors',
      expect.objectContaining({
        metricKeys: ['period_overall_amount', 'period_buyers', 'period_impression_view_rate'],
      }),
    ),
  )
  expect(getAnchorHourDetails).toHaveBeenCalledWith(
    expect.objectContaining({
      metricKeys: ['period_overall_amount', 'period_buyers', 'period_impression_view_rate'],
    }),
    1,
    50,
  )
})

test('主播分析按 URL 指标筛选动态显示数据列并传给 API', async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[
          '/anchors?start=2026-07-08&end=2026-07-08&rooms=room-1&metrics=period_buyers',
        ]}
      >
        <AnalysisPage dimension="anchors" />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  expect(await screen.findAllByRole('columnheader', { name: '时段成交人数' })).toHaveLength(2)
  expect(screen.queryByRole('columnheader', { name: '时段整体成交金额' })).not.toBeInTheDocument()
  expect(screen.getByText('已选 1 个指标')).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: '指标' })).toBeInTheDocument()
  expect(screen.getByLabelText('快捷周期')).toBeInTheDocument()
  expect(screen.getByText('主播时段明细')).toBeInTheDocument()
  expect(await screen.findByRole('columnheader', { name: '自然小时' })).toBeInTheDocument()
  expect(screen.getByRole('cell', { name: '测试直播间' })).toBeInTheDocument()
  expect(screen.getByText('当前筛选范围共 1 条时段数据')).toBeInTheDocument()
  expect(getAnalysis).toHaveBeenCalledWith(
    'anchors',
    expect.objectContaining({
      roomIds: ['room-1'],
      metricKeys: ['period_buyers'],
    }),
  )
  expect(getAnchorHourDetails).toHaveBeenCalledWith(
    expect.objectContaining({
      roomIds: ['room-1'],
      metricKeys: ['period_buyers'],
    }),
    1,
    50,
  )

  fireEvent.click(screen.getByRole('button', { name: '查看Q-李昕的全部时段数据' }))
  await waitFor(() =>
    expect(getAnchorHourDetails).toHaveBeenLastCalledWith(
      expect.objectContaining({ anchors: ['Q-李昕'] }),
      1,
      50,
    ),
  )
})
