import { render, screen } from '@testing-library/react'
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
      supports_hourly_trend: true,
      supports_kline: true,
      supports_alerts: false,
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
      period_buyers: 8,
    },
  ]),
}))

import { getAnalysis } from '@/api/client'
import { AnalysisPage } from './AnalysisPage'

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

  expect(await screen.findByRole('columnheader', { name: '时段成交人数' })).toBeInTheDocument()
  expect(screen.queryByRole('columnheader', { name: '时段整体成交金额' })).not.toBeInTheDocument()
  expect(screen.getByText('已选 1 个指标')).toBeInTheDocument()
  expect(screen.getByRole('combobox', { name: '指标' })).toBeInTheDocument()
  expect(screen.getByLabelText('快捷周期')).toBeInTheDocument()
  expect(getAnalysis).toHaveBeenCalledWith(
    'anchors',
    expect.objectContaining({
      roomIds: ['room-1'],
      metricKeys: ['period_buyers'],
    }),
  )
})
