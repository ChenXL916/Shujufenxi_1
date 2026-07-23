import { useQuery } from '@tanstack/react-query'
import { Button, Card, Segmented, Select, Space, Tag, Typography } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getDetail, getFilterOptions, getTimeline } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { MetricChart } from '@/components/MetricChart'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { DataPointDetailDrawer } from '@/features/timeline/DataPointDetailDrawer'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import type { TimelineGroup, XItem } from '@/types/dashboard'
import { groupSeriesByUnit } from '@/utils/format'
import { restoreFocusAfterOverlayClose } from '@/utils/focus'
import { mergeTimelineGroups } from '@/utils/timeline'

function pointForIndex(group: TimelineGroup, index: number): XItem | null {
  return (
    group.series
      .map((series) => series.source_items?.[index] ?? null)
      .find((item): item is XItem => Boolean(item)) ??
    group.x_items[index] ??
    null
  )
}

export function TimelinePage() {
  const { filters, update, reset } = useDashboardFilters()
  const [selected, setSelected] = useState<XItem | null>(null)
  const [keyboardSelection, setKeyboardSelection] = useState<{
    groupKey: string
    index: number
    point: XItem
  } | null>(null)
  const detailTriggerRef = useRef<HTMLElement | null>(null)
  const closeDetail = () => {
    const trigger = detailTriggerRef.current
    setSelected(null)
    restoreFocusAfterOverlayClose(trigger)
  }
  const [mergeRooms, setMergeRooms] = useState(false)
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  useEffect(() => {
    if (!filters.metricKeys.length && options.data) {
      update({
        metricKeys: options.data.metrics
          .filter((metric) => metric.default_visible)
          .slice(0, 4)
          .map((metric) => metric.key),
      })
    }
  }, [filters.metricKeys.length, options.data, update])
  const timeline = useQuery({
    queryKey: ['timeline', filters],
    queryFn: () => getTimeline(filters),
    enabled: Boolean(filters.startDate && filters.metricKeys.length),
  })
  const detailId = selected
    ? filters.grain === 'hour'
      ? selected.fact_id
      : selected.point_id
    : null
  const detail = useQuery({
    queryKey: ['detail', filters.grain, detailId],
    queryFn: () => getDetail(detailId!, filters.grain),
    enabled: Boolean(detailId),
  })
  const groups = useMemo(() => timeline.data?.groups ?? [], [timeline.data])
  useEffect(() => {
    if (groups.length < 2 && mergeRooms) setMergeRooms(false)
  }, [groups.length, mergeRooms])
  const displayGroups = useMemo(
    () => (mergeRooms && groups.length > 1 ? [mergeTimelineGroups(groups, filters.grain)] : groups),
    [filters.grain, groups, mergeRooms],
  )
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader
        title="小时趋势"
        description="X 轴按日期 → 自然小时 → 真实采集时间排序"
        eyebrow="HOURLY TELEMETRY"
        actions={
          <Segmented
            value={mergeRooms ? 'merge' : 'split'}
            options={[
              { label: '按直播间拆图', value: 'split' },
              { label: '合并系列', value: 'merge', disabled: groups.length < 2 },
            ]}
            onChange={(value) => setMergeRooms(value === 'merge')}
          />
        }
      />
      <FilterBar
        options={options.data}
        filters={filters}
        update={update}
        reset={reset}
        showMetrics
      />
      {timeline.isLoading ? (
        <LoadingPanel />
      ) : timeline.isError ? (
        <ErrorPanel onRetry={() => void timeline.refetch()} />
      ) : !groups.length ? (
        <EmptyPanel />
      ) : (
        displayGroups.map((group) => (
          <Card
            key={group.group_key}
            title={group.group_label}
            className="chart-card"
            extra={<Tag>{filters.grain === 'hour' ? '自然小时' : '真实采集点'}</Tag>}
          >
            {Object.entries(groupSeriesByUnit(group.series)).map(([unit, series]) => (
              <section key={unit} className="unit-chart">
                <Typography.Text className="unit-label">{unit}</Typography.Text>
                <MetricChart
                  group={group}
                  series={series}
                  onPointClick={(index, clickedSeries) => {
                    detailTriggerRef.current = null
                    setSelected(clickedSeries.source_items?.[index] ?? group.x_items[index] ?? null)
                  }}
                />
              </section>
            ))}
            <div className="timeline-keyboard-access">
              <Typography.Text type="secondary">键盘查看数据点</Typography.Text>
              <Select<number>
                showSearch
                allowClear
                className="timeline-point-select"
                placeholder="选择数据点打开详情"
                aria-label={`${group.group_label}：选择数据点打开详情`}
                optionFilterProp="label"
                value={
                  keyboardSelection?.groupKey === group.group_key
                    ? keyboardSelection.index
                    : undefined
                }
                options={group.x_items.map((item, index) => {
                  const point = pointForIndex(group, index)
                  const detailKey =
                    filters.grain === 'hour' ? (point?.fact_id ?? null) : (point?.point_id ?? null)
                  return {
                    value: index,
                    label: item.label,
                    disabled: !detailKey,
                  }
                })}
                onSelect={(index) => {
                  const point = pointForIndex(group, index)
                  if (point) {
                    setKeyboardSelection({ groupKey: group.group_key, index, point })
                  }
                }}
              />
              <Button
                disabled={keyboardSelection?.groupKey !== group.group_key}
                aria-label={`${group.group_label}：打开所选数据点详情`}
                onClick={(event) => {
                  if (keyboardSelection?.groupKey !== group.group_key) return
                  detailTriggerRef.current = event.currentTarget
                  setSelected(keyboardSelection.point)
                }}
              >
                打开详情
              </Button>
            </div>
          </Card>
        ))
      )}
      <DataPointDetailDrawer
        open={Boolean(selected)}
        onClose={closeDetail}
        loading={detail.isLoading}
        error={detail.isError}
        onRetry={() => void detail.refetch()}
        detail={detail.data}
        filterOptions={options.data}
        grain={filters.grain}
      />
    </Space>
  )
}
