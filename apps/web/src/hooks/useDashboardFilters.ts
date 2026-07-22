import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { DashboardFilters } from '@/types/dashboard'

const list = (value: string | null) => value?.split(',').filter(Boolean) ?? []

export function useDashboardFilters() {
  const [search, setSearch] = useSearchParams()
  const filters = useMemo<DashboardFilters>(
    () => ({
      startDate: search.get('start') ?? undefined,
      endDate: search.get('end') ?? undefined,
      dateMode: search.get('date_mode') === 'month' ? 'month' : 'day',
      roomIds: list(search.get('rooms')),
      anchors: list(search.get('anchors')),
      anchorMembers: list(search.get('anchor_members')),
      controls: list(search.get('controls')),
      hours: list(search.get('hours')),
      metricKeys: list(search.get('metrics')),
      grain: search.get('grain') === 'point' ? 'point' : 'hour',
    }),
    [search],
  )
  const update = useCallback(
    (patch: Partial<DashboardFilters>) => {
      const next = { ...filters, ...patch }
      const params = new URLSearchParams()
      for (const [key, value] of search.entries()) {
        if (key.startsWith('hc_')) params.set(key, value)
      }
      if (next.startDate) params.set('start', next.startDate)
      if (next.endDate) params.set('end', next.endDate)
      if (next.dateMode === 'month') params.set('date_mode', 'month')
      if (next.roomIds.length) params.set('rooms', next.roomIds.join(','))
      if (next.anchors.length) params.set('anchors', next.anchors.join(','))
      if (next.anchorMembers.length) params.set('anchor_members', next.anchorMembers.join(','))
      if (next.controls.length) params.set('controls', next.controls.join(','))
      if (next.hours.length) params.set('hours', next.hours.join(','))
      if (next.metricKeys.length) params.set('metrics', next.metricKeys.join(','))
      if (next.grain !== 'hour') params.set('grain', next.grain)
      setSearch(params, { replace: true })
    },
    [filters, search, setSearch],
  )
  const reset = useCallback(() => setSearch({}, { replace: true }), [setSearch])
  return { filters, update, reset }
}
