import { fireEvent, render, screen } from '@testing-library/react'
import type { DetailResponse, FilterOptions, MetricOption } from '@/types/dashboard'
import { DataPointDetailDrawer } from './DataPointDetailDrawer'

const metrics: MetricOption[] = [
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
    default_visible: true,
    analysis_default: true,
    supports_hourly_trend: true,
    supports_kline: false,
    supports_alerts: true,
    is_cumulative: false,
  },
  {
    key: 'period_overall_roi',
    name: '时段整体支付ROI',
    category: 'ROI',
    unit: 'ratio',
    precision: 2,
    scope: 'derived',
    aggregation: 'RATIO_OF_SUMS',
    numerator: 'period_overall_amount',
    denominator: 'period_spend',
    direction: 'higher_better',
    default_visible: true,
    analysis_default: true,
    supports_hourly_trend: true,
    supports_kline: true,
    supports_alerts: true,
    is_cumulative: false,
  },
  {
    key: 'room_viewers',
    name: '直播间观看人数',
    category: '人数',
    unit: 'count',
    precision: 0,
    scope: 'cumulative',
    aggregation: 'LAST_PER_ROOM_DAY',
    numerator: null,
    denominator: null,
    direction: 'higher_better',
    default_visible: false,
    analysis_default: false,
    supports_hourly_trend: false,
    supports_kline: false,
    supports_alerts: false,
    is_cumulative: true,
  },
]

const filterOptions: FilterOptions = {
  min_date: '2026-07-22',
  max_date: '2026-07-22',
  months: ['2026-07'],
  rooms: [],
  anchors: [],
  anchor_members: [],
  controls: [],
  hour_slots: ['11-12'],
  metrics,
  comparison_types: [],
}

const detail: DetailResponse = {
  id: 'fact-1',
  room: '柏瑞美-散粉',
  base: {
    date: '2026-07-22',
    hour_slot: '11-12',
    anchor: 'Q-儿儿',
    control: '郑荣喜',
    planned_anchor: 'Q-儿儿',
    anchor_match_status: 'matched',
    data_status: 'complete',
    latest_observed_at: '2026-07-22T11:00:00+08:00',
  },
  metrics: {
    period_overall_amount: '8328.60',
    period_overall_roi: '1.94',
    room_viewers: '146900',
  },
  raw_payload: { 原始字段: '原始值' },
  points: [
    {
      id: 'point-1',
      observed_at: '2026-07-22T10:35:00+08:00',
      valid: true,
      invalid_reason: null,
    },
    {
      id: 'point-2',
      observed_at: '2026-07-22T11:00:00+08:00',
      valid: false,
      invalid_reason: '字段缺失',
    },
  ],
}

describe('DataPointDetailDrawer', () => {
  it('uses Chinese context labels, status language, grouped metrics, and source-point layout', () => {
    render(
      <DataPointDetailDrawer
        detail={detail}
        filterOptions={filterOptions}
        grain="hour"
        loading={false}
        error={false}
        open
        onClose={() => undefined}
        onRetry={() => undefined}
      />,
    )

    expect(screen.getByRole('dialog', { name: '数据点详情' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '柏瑞美-散粉' })).toBeInTheDocument()
    expect(screen.getByText('自然小时汇总')).toBeInTheDocument()
    expect(screen.getByText('数据完整')).toBeInTheDocument()
    expect(screen.getByText('排班一致')).toBeInTheDocument()
    expect(screen.getByText('本时段表现')).toBeInTheDocument()
    expect(screen.getByText('直播累计')).toBeInTheDocument()
    expect(screen.getByText('¥8,328.60')).toBeInTheDocument()
    expect(screen.getByText('1.94')).toBeInTheDocument()
    expect(screen.getByText('146,900')).toBeInTheDocument()
    expect(screen.getByText('2 个采集点')).toBeInTheDocument()
    expect(screen.getByText('字段缺失')).toBeInTheDocument()
    expect(screen.queryByText('hour_slot')).not.toBeInTheDocument()
    expect(screen.queryByText('anchor_match_status')).not.toBeInTheDocument()
  })

  it('keeps the original payload available without expanding it by default', () => {
    render(
      <DataPointDetailDrawer
        detail={detail}
        filterOptions={filterOptions}
        grain="hour"
        loading={false}
        error={false}
        open
        onClose={() => undefined}
        onRetry={() => undefined}
      />,
    )

    expect(screen.getByText('原始字段')).toBeInTheDocument()
    expect(screen.queryByText(/"原始字段": "原始值"/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('原始字段'))
    expect(screen.getByText(/"原始字段": "原始值"/)).toBeInTheDocument()
  })
})
