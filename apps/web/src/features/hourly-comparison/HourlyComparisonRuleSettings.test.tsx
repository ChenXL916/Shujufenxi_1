import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

const api = vi.hoisted(() => ({
  createHourlyComparisonRule: vi.fn(),
  getHourlyComparisonRules: vi.fn(),
  updateHourlyComparisonRule: vi.fn(),
}))

vi.mock('@/api/client', () => api)

import { HourlyComparisonRuleSettings } from './HourlyComparisonRuleSettings'

const legacyRule = {
  id: 'rule-1',
  name: '旧版1天小时ROI与消耗周期对比',
  rule_type: 'hourly_comparison_legacy' as const,
  period_days: 1 as const,
  spend_increase_threshold: '0.30',
  spend_decrease_threshold: '-0.30',
  roi_increase_threshold: '0.30',
  roi_decrease_threshold: '-0.30',
  minimum_spend: '100',
  minimum_orders: 3,
  minimum_coverage_rate: '0.80',
  minimum_effective_hours: 6,
  evaluation_delay_minutes: 15,
  push_schedule: 'weekly:1@09:30',
  schedule_timezone: 'Asia/Shanghai' as const,
  applicable_rooms: ['room-1'],
  applicable_anchors: ['主播甲'],
  enabled: true,
  push_enabled: true,
  push_chat_id: 'oc_business_group',
  send_rise: true,
  send_fall: false,
  rise_limit: 8,
  fall_limit: 6,
  send_empty_summary: false,
  allow_force_resend: true,
  push_retry_limit: 4,
  cooldown_minutes: 60,
  created_at: '2026-07-16T00:00:00+08:00',
  updated_at: '2026-07-16T00:00:00+08:00',
  created_by: null,
  updated_by: null,
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <HourlyComparisonRuleSettings />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getHourlyComparisonRules.mockResolvedValue([legacyRule])
  api.createHourlyComparisonRule.mockResolvedValue(legacyRule)
  api.updateHourlyComparisonRule.mockResolvedValue(legacyRule)
})

test('表格显式区分旧版规则和主播趋势规则', async () => {
  renderSettings()

  expect(await screen.findByText('旧版1天小时ROI与消耗周期对比')).toBeInTheDocument()
  expect(screen.getByText('旧版小时比较')).toBeInTheDocument()
  expect(screen.getByText('每周一 09:30')).toBeInTheDocument()
  expect(screen.getByText('飞书开启')).toBeInTheDocument()
})

test('编辑表单承载全部趋势推送字段并保持旧规则类型不变', async () => {
  renderSettings()
  fireEvent.click(await screen.findByRole('button', { name: /编\s*辑/ }))

  expect(await screen.findByText('编辑预警规则')).toBeInTheDocument()
  expect(screen.getByLabelText('规则类型')).toBeDisabled()
  expect(screen.getByLabelText('周期')).toBeDisabled()
  expect(screen.getByLabelText('最小有效小时')).toHaveValue('6')
  expect(screen.getByLabelText('推送计划')).toHaveValue('weekly:1@09:30')
  expect(screen.getByLabelText('计划时区')).toBeDisabled()
  expect(screen.getByLabelText('发送上涨榜')).toBeChecked()
  expect(screen.getByLabelText('发送下跌榜')).not.toBeChecked()
  expect(screen.getByLabelText('上涨榜最多人数')).toHaveValue('8')
  expect(screen.getByLabelText('下跌榜最多人数')).toHaveValue('6')
  expect(screen.getByLabelText('空榜也发送摘要')).not.toBeChecked()
  expect(screen.getByLabelText('允许强制重发')).toBeChecked()
  expect(screen.getByLabelText('推送重试上限')).toHaveValue('4')

  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }))
  await waitFor(() => expect(api.updateHourlyComparisonRule).toHaveBeenCalledOnce())
  expect(api.updateHourlyComparisonRule).toHaveBeenCalledWith(
    'rule-1',
    expect.objectContaining({
      rule_type: 'hourly_comparison_legacy',
      minimum_effective_hours: 6,
      push_schedule: 'weekly:1@09:30',
      schedule_timezone: 'Asia/Shanghai',
      send_rise: true,
      send_fall: false,
      rise_limit: 8,
      fall_limit: 6,
      send_empty_summary: false,
      allow_force_resend: true,
      push_retry_limit: 4,
    }),
  )
}, 10_000)

test('新增规则默认创建主播趋势类型', async () => {
  api.getHourlyComparisonRules.mockResolvedValue([])
  renderSettings()

  fireEvent.click(await screen.findByRole('button', { name: '新增预警规则' }))
  expect(await screen.findByText('主播趋势汇总')).toBeInTheDocument()
  expect(screen.getByLabelText('规则类型')).not.toBeDisabled()
})
