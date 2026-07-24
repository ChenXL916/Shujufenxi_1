import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import type { TimelineGroup, TimelineSeries } from '@/types/dashboard'

const chartCapture = vi.hoisted(() => ({
  option: null as Record<string, unknown> | null,
  click: null as
    ((params: { dataIndex: number; seriesId?: string; seriesIndex: number }) => void) | null,
}))

vi.mock('@/components/ECharts', () => ({
  ECharts: ({
    option,
    onEvents,
  }: {
    option: Record<string, unknown>
    onEvents?: {
      click?: (params: { dataIndex: number; seriesId?: string; seriesIndex: number }) => void
    }
  }) => {
    chartCapture.option = option
    chartCapture.click = onEvents?.click ?? null
    return (
      <button
        type="button"
        onClick={() =>
          chartCapture.click?.({ dataIndex: 1, seriesId: 'timeline-hit-0', seriesIndex: 1 })
        }
      >
        点击扩大热区
      </button>
    )
  },
}))

import { MetricChart } from './MetricChart'

const group: TimelineGroup = {
  group_key: 'room-1',
  group_label: '测试直播间',
  x_items: [
    {
      key: '08-09',
      fact_id: 'fact-1',
      point_id: null,
      label: '08-09\n主播甲',
      date: '2026-07-08',
      hour_slot: '08-09',
      anchor: '主播甲',
      control: '场控甲',
      observed_at: null,
    },
    {
      key: '09-10',
      fact_id: 'fact-2',
      point_id: null,
      label: '09-10\n主播甲',
      date: '2026-07-08',
      hour_slot: '09-10',
      anchor: '主播甲',
      control: '场控甲',
      observed_at: null,
    },
  ],
  series: [],
  annotations: [],
}

const timelineSeries: TimelineSeries = {
  metric_key: 'period_overall_amount',
  name: '时段整体成交金额',
  unit: 'currency',
  axis_group: 'currency',
  data: [100, 200],
}

test('小时趋势为每个点提供24px热区且热区点击仍映射原系列', () => {
  const onPointClick = vi.fn()
  render(<MetricChart group={group} series={[timelineSeries]} onPointClick={onPointClick} />)

  const chartSeries = chartCapture.option?.series as Array<Record<string, unknown>>
  const hitTarget = chartSeries.find((item) => item.id === 'timeline-hit-0')
  expect(hitTarget).toEqual(
    expect.objectContaining({
      symbolSize: 24,
      cursor: 'pointer',
      showSymbol: true,
    }),
  )

  fireEvent.click(screen.getByRole('button', { name: '点击扩大热区' }))
  expect(onPointClick).toHaveBeenCalledWith(1, timelineSeries)
})
