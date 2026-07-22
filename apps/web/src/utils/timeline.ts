import type { Grain, TimelineGroup, TimelineSeries, XItem } from '@/types/dashboard'

interface IndexedItem {
  axisKey: string
  sortKey: string
  item: XItem
  index: number
}

function hourOrder(hourSlot: string | null): number {
  const start = Number.parseInt(hourSlot?.split('-', 1)[0] ?? '', 10)
  return Number.isNaN(start) ? 99 : start
}

function baseAxisKey(item: XItem, grain: Grain): string {
  if (grain === 'hour') return `${item.date}|${item.hour_slot ?? item.key}`
  return item.key
}

function itemSortKey(item: XItem, grain: Grain, occurrence: number): string {
  if (grain === 'hour') {
    return `${item.date}|${String(hourOrder(item.hour_slot)).padStart(2, '0')}|${occurrence}`
  }
  return `${item.observed_at ?? `${item.date}|${item.key}`}|${item.key}|${occurrence}`
}

function indexItems(group: TimelineGroup, grain: Grain): IndexedItem[] {
  const occurrences = new Map<string, number>()
  return group.x_items.map((item, index) => {
    const baseKey = baseAxisKey(item, grain)
    const occurrence = occurrences.get(baseKey) ?? 0
    occurrences.set(baseKey, occurrence + 1)
    return {
      axisKey: `${baseKey}|occurrence:${occurrence}`,
      sortKey: itemSortKey(item, grain, occurrence),
      item,
      index,
    }
  })
}

function mergedXItem(indexed: IndexedItem): XItem {
  return {
    ...indexed.item,
    key: `merged:${indexed.axisKey}`,
    fact_id: null,
    point_id: null,
    anchor: null,
    control: null,
    label: indexed.item.label.split('\n', 1)[0] ?? indexed.item.label,
  }
}

export function mergeTimelineGroups(groups: TimelineGroup[], grain: Grain): TimelineGroup {
  const indexedGroups = groups.map((group) => ({ group, items: indexItems(group, grain) }))
  const axisByKey = new Map<string, IndexedItem>()
  indexedGroups.forEach(({ items }) => {
    items.forEach((item) => {
      if (!axisByKey.has(item.axisKey)) axisByKey.set(item.axisKey, item)
    })
  })
  const axis = [...axisByKey.values()].sort((left, right) =>
    left.sortKey.localeCompare(right.sortKey),
  )

  const series: TimelineSeries[] = indexedGroups.flatMap(({ group, items }) => {
    const itemByKey = new Map(items.map((item) => [item.axisKey, item]))
    return group.series.map((sourceSeries) => ({
      ...sourceSeries,
      name: `${group.group_label} · ${sourceSeries.name}`,
      data: axis.map((axisItem) => {
        const sourceItem = itemByKey.get(axisItem.axisKey)
        return sourceItem ? (sourceSeries.data[sourceItem.index] ?? null) : null
      }),
      source_items: axis.map((axisItem) => itemByKey.get(axisItem.axisKey)?.item ?? null),
    }))
  })

  return {
    group_key: 'merged-rooms',
    group_label: '直播间合并对比',
    x_items: axis.map(mergedXItem),
    series,
    annotations: groups.flatMap((group) => group.annotations ?? []),
  }
}
