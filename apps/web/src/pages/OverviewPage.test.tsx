import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('@/api/client', () => ({
  getFilterOptions: vi.fn().mockResolvedValue({
    min_date: '2026-07-15',
    max_date: '2026-07-15',
    months: ['2026-07'],
    rooms: [],
    anchors: [],
    anchor_members: [],
    controls: [],
    hour_slots: [],
    metrics: [],
    comparison_types: ['previous_day'],
  }),
  getOverview: vi.fn().mockResolvedValue({
    start_date: '2026-07-15',
    end_date: '2026-07-15',
    kpis: [
      {
        metric_key: 'period_overall_roi',
        name: '时段整体ROI',
        unit: 'ratio',
        precision: 2,
        direction: 'higher_better',
        value: null,
        comparison: {
          current_value: null,
          baseline_value: null,
          delta_value: null,
          ratio_percent: null,
          growth_percent: null,
          direction_status: 'no_data',
          explanation: '待补录',
        },
      },
    ],
    room_ranking: [],
    anchor_match_rate: 1,
    data_completeness: null,
    data_submission_deadline_hour: 8,
    active_alerts: 0,
    sync_mode: 'feishu',
  }),
  getHourlyComparison: vi.fn().mockResolvedValue({
    meta: {
      timezone: 'Asia/Shanghai',
      generated_at: '2026-07-16T12:00:00+08:00',
      data_updated_at: null,
      period_days: 7,
      aggregation_mode: 'sum',
      chart_type: 'line',
      series_dimension: 'summary',
      include_today: false,
      compare_enabled: true,
    },
    current_period: { start: '2026-07-09', end: '2026-07-15', days: 7, complete: true },
    comparison_period: { start: '2026-07-02', end: '2026-07-08', days: 7, complete: true },
    hours: [],
    metrics: [],
    series: [],
  }),
  getHourlyComparisonDetails: vi.fn(),
  downloadHourlyComparison: vi.fn(),
}))

import { getOverview } from '@/api/client'
import { OverviewPage } from './OverviewPage'

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/overview?start=2026-07-15&end=2026-07-15']}>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('全为空值的KPI响应显示空态而不渲染占位卡片', async () => {
  const { container } = renderPage()

  expect(
    await screen.findByText('当前筛选条件下暂无实际数据，请调整日期、直播间或检查数据是否已同步。'),
  ).toBeInTheDocument()
  expect(screen.queryByText('0%')).not.toBeInTheDocument()
  expect(container.querySelectorAll('.kpi-card')).toHaveLength(0)
  expect(screen.queryByText('24小时ROI与消耗周期对比')).not.toBeInTheDocument()
})

test('合法零值KPI仍按有效数据渲染', async () => {
  vi.mocked(getOverview).mockResolvedValueOnce({
    start_date: '2026-07-15',
    end_date: '2026-07-15',
    kpis: [
      {
        metric_key: 'period_overall_roi',
        name: '时段整体ROI',
        unit: 'ratio',
        precision: 2,
        direction: 'higher_better',
        value: 0,
        comparison: {
          current_value: 0,
          baseline_value: null,
          delta_value: null,
          ratio_percent: null,
          growth_percent: null,
          direction_status: 'no_data',
          explanation: '有效零值',
        },
      },
    ],
    room_ranking: [],
    anchor_match_rate: 1,
    data_completeness: 1,
    data_submission_deadline_hour: 8,
    active_alerts: 0,
    sync_mode: 'feishu',
  })
  const { container } = renderPage()

  expect(await screen.findByText('时段整体ROI')).toBeInTheDocument()
  expect(container.querySelectorAll('.kpi-card')).toHaveLength(1)
  expect(screen.getByRole('region', { name: '核心经营指标' })).toHaveClass('kpi-grid')
  expect(container.querySelector('.hourly-primary-grid')).toBeInTheDocument()
  expect(screen.getByRole('complementary', { name: '趋势与预警摘要' })).toBeInTheDocument()
  expect(screen.getByText('数据与排班质量')).toBeInTheDocument()
})
