import type { TimelineGroup, XItem } from '@/types/dashboard'
import { mergeTimelineGroups } from './timeline'

function xItem(
  key: string,
  factId: string | null,
  pointId: string | null,
  date: string,
  hourSlot: string | null,
  observedAt: string | null,
): XItem {
  return {
    key,
    fact_id: factId,
    point_id: pointId,
    label: `${date} ${hourSlot ?? observedAt}`,
    date,
    hour_slot: hourSlot,
    anchor: '主播',
    control: '中控',
    observed_at: observedAt,
  }
}

function group(label: string, items: XItem[], data: Array<number | null>): TimelineGroup {
  return {
    group_key: label,
    group_label: label,
    x_items: items,
    series: [
      {
        metric_key: 'period_overall_roi',
        name: '整体ROI',
        unit: 'ratio',
        axis_group: 'ratio',
        data,
      },
    ],
    annotations: [],
  }
}

test('aligns merged room series by business date and natural hour', () => {
  const roomA = group(
    'A直播间',
    [
      xItem('a-9', 'a9', null, '2026-07-14', '9-10', '2026-07-14T09:55:00'),
      xItem('a-10', 'a10', null, '2026-07-14', '10-11', '2026-07-14T10:55:00'),
    ],
    [1, 2],
  )
  const roomB = group(
    'B直播间',
    [
      xItem('b-9', 'b9', null, '2026-07-14', '9-10', '2026-07-14T09:58:00'),
      xItem('b-11', 'b11', null, '2026-07-14', '11-12', '2026-07-14T11:58:00'),
    ],
    [3, 4],
  )

  const merged = mergeTimelineGroups([roomA, roomB], 'hour')

  expect(merged.group_label).toBe('直播间合并对比')
  expect(merged.x_items.map((item) => item.hour_slot)).toEqual(['9-10', '10-11', '11-12'])
  expect(merged.series.map((series) => series.name)).toEqual([
    'A直播间 · 整体ROI',
    'B直播间 · 整体ROI',
  ])
  expect(merged.series[0]?.data).toEqual([1, 2, null])
  expect(merged.series[1]?.data).toEqual([3, null, 4])
  expect(merged.series[1]?.source_items?.map((item) => item?.fact_id ?? null)).toEqual([
    'b9',
    null,
    'b11',
  ])
})

test('preserves duplicate real samples instead of fabricating or collapsing points', () => {
  const duplicate = xItem(
    '2026-07-14T09:30:00|主播',
    null,
    'point-1',
    '2026-07-14',
    '9-10',
    '2026-07-14T09:30:00',
  )
  const duplicateTwo = { ...duplicate, point_id: 'point-2' }
  const merged = mergeTimelineGroups([group('A直播间', [duplicate, duplicateTwo], [1, 2])], 'point')

  expect(merged.x_items).toHaveLength(2)
  expect(merged.series[0]?.data).toEqual([1, 2])
  expect(merged.series[0]?.source_items?.map((item) => item?.point_id)).toEqual([
    'point-1',
    'point-2',
  ])
})
