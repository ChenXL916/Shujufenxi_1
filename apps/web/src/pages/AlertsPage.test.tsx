import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, vi } from 'vitest'

const api = vi.hoisted(() => ({
  acknowledgeAlert: vi.fn(),
  evaluateAlerts: vi.fn(),
  getAlertEvents: vi.fn(),
  getAnchorTrendEvent: vi.fn(),
  getAnchorTrends: vi.fn(),
  getCurrentUser: vi.fn(),
  getFilterOptions: vi.fn(),
  recalculateAnchorTrends: vi.fn(),
  retryAlertPush: vi.fn(),
  sendAnchorTrendSummary: vi.fn(),
  testAlertPush: vi.fn(),
  testAnchorTrendPush: vi.fn(),
}))
const antdMessage = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/api/client', () => api)
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, message: antdMessage }
})

import { AlertsPage } from './AlertsPage'

const riseItem = {
  item_id: 'item-rise',
  event_id: 'event-rise',
  rank: 1,
  room_id: 'room-1',
  room_name: '一号直播间',
  anchor_id: 'anchor-1',
  anchor_name: '主播甲',
  control_names: ['场控甲'],
  trend_type: 'rise' as const,
  current_amount: '390',
  baseline_amount: '300',
  current_spend: '200',
  baseline_spend: '200',
  spend_growth_rate: '0',
  current_roi: '1.95',
  baseline_roi: '1.50',
  roi_growth_rate: '0.30',
  current_orders: '30',
  baseline_orders: '20',
  current_order_cost: '6.67',
  baseline_order_cost: '10',
  roi_target: '1.81',
  roi_target_gap: '0.14',
  roi_target_reached: true,
  primary_status: 'roi_rise',
  primary_status_name: 'ROI显著上涨',
  reason_codes: ['roi_rise'],
  reasons: ['ROI较基准上涨30%'],
  major_rise_hours: ['08-09', '09-10'],
  major_fall_hours: [],
  major_spend_hours: ['10-11'],
  hourly_details: [],
  current_effective_days: 3,
  baseline_effective_days: 3,
  current_effective_hours: 18,
  baseline_effective_hours: 20,
  current_coverage_rate: '0.90',
  baseline_coverage_rate: '1.00',
  comparison_basis: '等长完整自然日汇总',
  suggestion: '复盘主要上涨时段。',
  push_status: 'pending',
  destination_group: '运营群',
}

const fallItem = {
  ...riseItem,
  item_id: 'item-fall',
  event_id: 'event-fall',
  anchor_id: 'anchor-2',
  anchor_name: '主播乙',
  trend_type: 'fall' as const,
  current_roi: '1.40',
  baseline_roi: '2.00',
  roi_growth_rate: '-0.30',
  roi_target_gap: '-0.41',
  roi_target_reached: false,
  primary_status: 'roi_fall',
  primary_status_name: 'ROI显著下跌',
  reasons: ['ROI较基准下跌30%'],
  major_rise_hours: [],
  major_fall_hours: ['20-21'],
  push_status: 'sent',
}

const insufficientItem = {
  ...riseItem,
  item_id: 'item-insufficient',
  event_id: 'event-insufficient',
  anchor_id: 'anchor-3',
  anchor_name: '主播丙',
  trend_type: 'insufficient' as const,
  current_roi: null,
  baseline_roi: null,
  roi_growth_rate: null,
  roi_target_reached: null,
  primary_status: 'sample_insufficient',
  primary_status_name: '样本不足',
  reasons: ['当前周期或基准周期有效直播小时不足'],
  current_effective_hours: 1,
  baseline_effective_hours: 0,
  current_coverage_rate: '0.20',
  baseline_coverage_rate: '0',
}

const riseEvent = {
  id: 'event-rise',
  rule_id: 'rule-1',
  period_days: 3,
  current_period_start: '2026-07-13',
  current_period_end: '2026-07-15',
  baseline_period_start: '2026-07-10',
  baseline_period_end: '2026-07-12',
  notification_type: 'anchor_rise_summary' as const,
  destination_group: '运营群',
  room_scope: ['room-1'],
  anchor_count: 1,
  dedup_key: 'dedup-rise',
  push_status: 'pending',
  push_attempts: 0,
  pushed_at: null,
  push_error: null,
  manual_resend: false,
  source_event_id: null,
  resend_reason: null,
  operated_by: null,
  created_at: '2026-07-16T09:30:00+08:00',
}

const trendResponse = {
  current_period: { start: '2026-07-13', end: '2026-07-15' },
  baseline_period: { start: '2026-07-10', end: '2026-07-12' },
  rise: [riseItem],
  fall: [fallItem],
  insufficient: [insufficientItem],
  summary: { rise_count: 1, fall_count: 1, insufficient_count: 1, reached_count: 1 },
  events: [
    riseEvent,
    {
      ...riseEvent,
      id: 'event-fall',
      notification_type: 'anchor_fall_summary' as const,
      push_status: 'sent',
    },
  ],
}

const detailResponse = {
  event: riseEvent,
  items: [riseItem],
  details: [
    {
      item_id: 'item-rise',
      daily: [
        {
          period: 'current' as const,
          date: '2026-07-15',
          spend: '200',
          amount: '390',
          roi: '1.95',
          orders: '30',
        },
      ],
      hours: [
        {
          hour: '08-09',
          current: { spend: '100', amount: '195', roi: '1.95', orders: '15' },
          baseline: { spend: '100', amount: '150', roi: '1.50', orders: '10' },
          roi_delta: '0.45',
          spend_difference: '0',
        },
      ],
      roi_numerator: { current: '390', baseline: '300' },
      roi_denominator: { current: '200', baseline: '200' },
      raw_records: [
        {
          fact_id: 'fact-1',
          period: 'current',
          date: '2026-07-15',
          natural_hour: '08-09',
          anchor: '主播甲',
          control: '场控甲',
          data_status: 'complete',
          metrics: { period_spend: '100', period_overall_amount: '195' },
        },
      ],
    },
  ],
}

const filterOptions = {
  min_date: '2026-07-01',
  max_date: '2026-07-15',
  months: ['2026-07'],
  rooms: [{ id: 'room-1', name: '一号直播间' }],
  anchors: ['主播甲', '主播乙', '主播丙'],
  anchor_members: [],
  controls: ['场控甲'],
  hour_slots: ['08-09'],
  metrics: [],
  comparison_types: [],
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-search">{location.search}</output>
}

function renderPage(entry = '/alerts?tab=rise&period_days=3') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <LocationProbe />
        <Routes>
          <Route path="/alerts" element={<AlertsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getCurrentUser.mockResolvedValue({
    id: null,
    name: '开发管理员',
    role: 'developer',
    permissions: ['*'],
    room_ids: null,
    room_names: ['全部直播间'],
    scope_label: '全部直播间',
    can_export: true,
    can_manage_permissions: true,
    can_manage_system: true,
    can_manage_alerts: true,
    can_sync: true,
    auth_mode: 'development_bypass',
  })
  api.getFilterOptions.mockResolvedValue(filterOptions)
  api.getAnchorTrends.mockResolvedValue(trendResponse)
  api.getAnchorTrendEvent.mockResolvedValue(detailResponse)
  api.getAlertEvents.mockResolvedValue([])
  api.recalculateAnchorTrends.mockResolvedValue(trendResponse)
  api.testAnchorTrendPush.mockResolvedValue({ push_status: 'skipped', provider: {}, payload: {} })
  api.sendAnchorTrendSummary.mockResolvedValue({ event_id: 'event-rise', push_status: 'skipped' })
  api.evaluateAlerts.mockResolvedValue({
    recovered: 0,
    created: 0,
    queued: 0,
    sent: 0,
    failed: 0,
    skipped: 0,
  })
})

test('默认展示主播上涨榜，并从 URL 恢复全部趋势筛选而不请求数据质量预警', async () => {
  renderPage(
    '/alerts?tab=rise&period_days=3&end_date=2026-07-15&room_ids=room-1&anchor_names=%E4%B8%BB%E6%92%AD%E7%94%B2&control_names=%E5%9C%BA%E6%8E%A7%E7%94%B2&roi_target_status=reached&minimum_coverage_rate=0.8&pushed=true',
  )

  expect(await screen.findByText('主播甲')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /主播上涨榜/ })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: /主播下跌榜/ })).toBeInTheDocument()
  expect(screen.getByText('90.0%')).toBeInTheDocument()
  expect(screen.getAllByText('已达标').length).toBeGreaterThan(0)
  expect(screen.getByText('08-09、09-10')).toBeInTheDocument()

  await waitFor(() =>
    expect(api.getAnchorTrends).toHaveBeenCalledWith(
      expect.objectContaining({
        period_days: 3,
        end_date: '2026-07-15',
        room_ids: ['room-1'],
        anchor_names: ['主播甲'],
        control_names: ['场控甲'],
        trend_type: 'all',
        roi_target_status: 'reached',
        minimum_coverage_rate: 0.8,
        pushed: true,
      }),
    ),
  )
  expect(api.getAlertEvents).not.toHaveBeenCalled()

  fireEvent.click(screen.getByRole('tab', { name: /主播下跌榜/ }))
  await waitFor(() =>
    expect(screen.getByTestId('location-search').textContent).toContain('tab=fall'),
  )
  expect(await screen.findByText('主播乙')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '主播上涨榜 1' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '主播下跌榜 1' })).toHaveAttribute('aria-selected', 'true')
})

test('详情抽屉展示逐日、24小时、ROI分子分母与原始事实', async () => {
  renderPage('/alerts?tab=rise&period_days=3&end_date=2026-07-15')

  fireEvent.click(await screen.findByRole('button', { name: '查看主播甲趋势详情' }))
  expect(await screen.findByText('主播甲｜趋势事实详情')).toBeInTheDocument()
  expect(await screen.findByText('当前周期 ROI 分子')).toBeInTheDocument()
  expect(screen.getAllByText('¥390.00').length).toBeGreaterThan(0)

  fireEvent.click(screen.getByRole('tab', { name: '逐日汇总' }))
  expect(await screen.findByText('2026-07-15')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('tab', { name: '24小时明细' }))
  expect(await screen.findByText('08-09')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('tab', { name: '原始事实' }))
  expect(await screen.findByText('fact-1')).toBeInTheDocument()
  expect(screen.getByText('有效')).toBeInTheDocument()
  expect(api.getAnchorTrendEvent).toHaveBeenCalledWith('event-rise')
})

test('运营可重算；管理员可测试、发送，并且强制重发必须填写原因', async () => {
  renderPage('/alerts?tab=rise&period_days=3&end_date=2026-07-15')
  await screen.findByText('主播甲')

  fireEvent.click(screen.getByRole('button', { name: '重算当前趋势' }))
  await waitFor(() =>
    expect(api.recalculateAnchorTrends).toHaveBeenCalledWith(
      expect.objectContaining({
        rule_id: 'rule-1',
        period_days: 3,
        end_date: '2026-07-15',
      }),
    ),
  )

  fireEvent.click(screen.getByRole('button', { name: '测试上涨榜推送' }))
  await waitFor(() =>
    expect(api.testAnchorTrendPush).toHaveBeenCalledWith({
      notification_type: 'anchor_rise_summary',
    }),
  )

  fireEvent.click(screen.getByRole('button', { name: '发送当前上涨榜' }))
  await waitFor(() =>
    expect(api.sendAnchorTrendSummary).toHaveBeenCalledWith({
      rule_id: 'rule-1',
      period: '2026-07-15',
      notification_type: 'anchor_rise_summary',
      force_resend: false,
    }),
  )

  api.sendAnchorTrendSummary.mockClear()
  fireEvent.click(screen.getByRole('button', { name: '强制重发当前上涨榜' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认强制重发' }))
  expect(await screen.findByText('请填写强制重发原因')).toBeInTheDocument()
  expect(api.sendAnchorTrendSummary).not.toHaveBeenCalled()

  fireEvent.change(screen.getByLabelText('强制重发原因'), {
    target: { value: '修正运营口径后重新通知' },
  })
  fireEvent.click(screen.getByRole('button', { name: '确认强制重发' }))
  await waitFor(() =>
    expect(api.sendAnchorTrendSummary).toHaveBeenCalledWith({
      rule_id: 'rule-1',
      period: '2026-07-15',
      notification_type: 'anchor_rise_summary',
      force_resend: true,
      resend_reason: '修正运营口径后重新通知',
    }),
  )
}, 15_000)

test('权限拒绝时显示独立权限状态而不是空表', async () => {
  api.getAnchorTrends.mockRejectedValue({ response: { status: 403 } })
  renderPage()

  expect(await screen.findByText('暂无主播趋势预警查看权限')).toBeInTheDocument()
  expect(screen.getByText('请联系管理员开通直播间或预警中心权限。')).toBeInTheDocument()
})

test('移动端使用无横向遮挡的主播趋势卡片并保留关键指标与详情入口', async () => {
  const mediaQuery = vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query === '(max-width: 768px)',
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )

  try {
    renderPage()

    expect(await screen.findByTestId('anchor-trend-mobile-list')).toBeInTheDocument()
    expect(screen.queryByTestId('anchor-trend-desktop-table')).not.toBeInTheDocument()
    expect(screen.getByText('当前 / 基准 ROI')).toBeInTheDocument()
    expect(screen.getByText('当前 / 基准消耗')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看主播甲趋势详情' })).toBeInTheDocument()
  } finally {
    mediaQuery.mockRestore()
  }
})
