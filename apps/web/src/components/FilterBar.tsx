import { CalendarOutlined, FilterOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons'
import { Button, DatePicker, Drawer, Segmented, Select, Space } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useRef, useState } from 'react'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import type { DashboardFilters, DateMode, FilterOptions, Grain } from '@/types/dashboard'
import { metricLabel } from '@/utils/format'
import { restoreFocusAfterOverlayClose } from '@/utils/focus'

interface Props {
  options?: FilterOptions
  filters: DashboardFilters
  update: (patch: Partial<DashboardFilters>) => void
  reset: () => void
  showMetrics?: boolean
  showGrain?: boolean
  showPeriodPresets?: boolean
}

const PERIOD_PRESETS = [1, 3, 5, 7, 15, 30] as const
const hiddenTagCount = (values: unknown[]) => `+${values.length}`

export function FilterBar({
  options,
  filters,
  update,
  reset,
  showMetrics = false,
  showGrain = showMetrics,
  showPeriodPresets = false,
}: Props) {
  const mobile = useMediaQuery('(max-width: 768px)')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const drawerTriggerRef = useRef<HTMLButtonElement | null>(null)
  const closeDrawer = () => {
    const trigger = drawerTriggerRef.current
    setDrawerOpen(false)
    restoreFocusAfterOverlayClose(trigger)
  }
  const selectedCount =
    filters.roomIds.length +
    filters.anchors.length +
    filters.anchorMembers.length +
    filters.controls.length +
    filters.hours.length +
    filters.metricKeys.length +
    (filters.startDate || filters.endDate ? 1 : 0)

  useEffect(() => {
    if (!mobile) setDrawerOpen(false)
  }, [mobile])

  useEffect(() => {
    if (!filters.startDate && options?.max_date) {
      const latest = dayjs(options.max_date)
      update(
        filters.dateMode === 'month'
          ? {
              startDate: latest.startOf('month').format('YYYY-MM-DD'),
              endDate: latest.endOf('month').format('YYYY-MM-DD'),
            }
          : { startDate: options.max_date, endDate: options.max_date },
      )
    }
  }, [filters.dateMode, filters.startDate, options?.max_date, update])

  const changeDateMode = (dateMode: DateMode) => {
    const reference = dayjs(filters.startDate ?? options?.max_date)
    update(
      dateMode === 'month'
        ? {
            dateMode,
            startDate: reference.startOf('month').format('YYYY-MM-DD'),
            endDate: reference.endOf('month').format('YYYY-MM-DD'),
          }
        : {
            dateMode,
            startDate: reference.format('YYYY-MM-DD'),
            endDate: reference.format('YYYY-MM-DD'),
          },
    )
  }

  const selectedPeriod =
    filters.startDate && filters.endDate
      ? dayjs(filters.endDate).diff(dayjs(filters.startDate), 'day') + 1
      : undefined

  const changePeriod = (days: number) => {
    const end = dayjs(filters.endDate ?? options?.max_date ?? filters.startDate)
    if (!end.isValid()) return
    update({
      dateMode: 'day',
      startDate: end.subtract(days - 1, 'day').format('YYYY-MM-DD'),
      endDate: end.format('YYYY-MM-DD'),
    })
  }

  const timeGroup = (
    <div className="filter-group filter-time-group">
      <div className="filter-group-label">
        <CalendarOutlined aria-hidden="true" />
        <span>时间范围</span>
      </div>
      <div className="filter-group-controls">
        <Segmented
          aria-label="日期筛选方式"
          value={filters.dateMode}
          options={[
            { label: '按日/范围', value: 'day' },
            { label: '按月', value: 'month' },
          ]}
          onChange={(value) => changeDateMode(value as DateMode)}
        />
        {showPeriodPresets ? (
          <Segmented
            aria-label="快捷周期"
            value={
              PERIOD_PRESETS.includes(selectedPeriod as (typeof PERIOD_PRESETS)[number])
                ? selectedPeriod
                : undefined
            }
            options={PERIOD_PRESETS.map((days) => ({ label: `${days}天`, value: days }))}
            onChange={(value) => changePeriod(Number(value))}
          />
        ) : null}
        {filters.dateMode === 'month' ? (
          <DatePicker
            picker="month"
            aria-label="月份"
            placeholder="选择月份"
            allowClear
            value={filters.startDate ? dayjs(filters.startDate) : null}
            disabledDate={(value) =>
              Boolean(options?.months.length) && !options?.months.includes(value.format('YYYY-MM'))
            }
            onChange={(value) =>
              update({
                startDate: value?.startOf('month').format('YYYY-MM-DD'),
                endDate: value?.endOf('month').format('YYYY-MM-DD'),
              })
            }
          />
        ) : (
          <DatePicker.RangePicker
            aria-label="日期范围"
            allowClear
            value={
              filters.startDate && filters.endDate
                ? [dayjs(filters.startDate), dayjs(filters.endDate)]
                : null
            }
            onChange={(dates) =>
              update({
                startDate: dates?.[0]?.format('YYYY-MM-DD'),
                endDate: dates?.[1]?.format('YYYY-MM-DD'),
              })
            }
          />
        )}
      </div>
    </div>
  )

  const scopeGroup = (
    <div className="filter-group filter-scope-group">
      <div className="filter-group-label">
        <TeamOutlined aria-hidden="true" />
        <span>业务范围</span>
      </div>
      <div className="filter-group-controls">
        <Select
          mode="multiple"
          maxTagCount={2}
          maxTagTextLength={12}
          maxTagPlaceholder={hiddenTagCount}
          placeholder="直播间"
          aria-label="直播间"
          value={filters.roomIds}
          options={options?.rooms.map((room) => ({ label: room.name, value: room.id }))}
          onChange={(roomIds) => update({ roomIds })}
          className="filter-select"
        />
        <Select
          mode="multiple"
          showSearch
          maxTagCount={2}
          maxTagTextLength={12}
          maxTagPlaceholder={hiddenTagCount}
          placeholder="主播"
          aria-label="主播"
          value={filters.anchors}
          options={options?.anchors.map((name) => ({ label: name, value: name }))}
          onChange={(anchors) => update({ anchors })}
          className="filter-select"
        />
        <Select
          mode="multiple"
          showSearch
          maxTagCount={2}
          maxTagTextLength={12}
          maxTagPlaceholder={hiddenTagCount}
          placeholder="主播成员"
          aria-label="主播成员"
          value={filters.anchorMembers}
          options={options?.anchor_members.map((name) => ({ label: name, value: name }))}
          onChange={(anchorMembers) => update({ anchorMembers })}
          className="filter-select"
        />
        <Select
          mode="multiple"
          showSearch
          maxTagCount={2}
          maxTagTextLength={12}
          maxTagPlaceholder={hiddenTagCount}
          placeholder="场控"
          aria-label="场控"
          value={filters.controls}
          options={options?.controls.map((name) => ({ label: name, value: name }))}
          onChange={(controls) => update({ controls })}
          className="filter-select"
        />
        <Select
          mode="multiple"
          maxTagCount={2}
          maxTagTextLength={12}
          maxTagPlaceholder={hiddenTagCount}
          placeholder="自然小时"
          aria-label="自然小时"
          value={filters.hours}
          options={options?.hour_slots.map((hour) => ({ label: hour, value: hour }))}
          onChange={(hours) => update({ hours })}
          className="filter-select hours"
        />
        {showMetrics ? (
          <Select
            mode="multiple"
            maxTagCount={2}
            maxTagTextLength={12}
            maxTagPlaceholder={hiddenTagCount}
            placeholder="指标（最多建议 4 个）"
            aria-label="指标"
            value={filters.metricKeys}
            options={options?.metrics.map((metric) => ({
              label: metricLabel(metric),
              value: metric.key,
              group: metric.category,
            }))}
            onChange={(metricKeys) => update({ metricKeys })}
            className="metric-select"
          />
        ) : null}
        {showMetrics && showGrain ? (
          <Segmented
            aria-label="数据粒度"
            value={filters.grain}
            options={[
              { label: '小时', value: 'hour' },
              { label: '采集点', value: 'point' },
            ]}
            onChange={(grain) => update({ grain: grain as Grain })}
          />
        ) : null}
      </div>
    </div>
  )

  return (
    <section className={`filter-bar${mobile ? ' filter-bar-mobile' : ''}`} aria-label="全局筛选">
      <div className="filter-heading">
        <div className="filter-heading-copy">
          <span className="filter-heading-icon" aria-hidden="true">
            <FilterOutlined />
          </span>
          <div>
            <strong>全局筛选</strong>
            <span>已选 {selectedCount} 项</span>
          </div>
        </div>
        <Button type="text" icon={<ReloadOutlined />} aria-label="清空全部筛选" onClick={reset}>
          清空
        </Button>
      </div>

      {mobile ? (
        <>
          <div className="filter-mobile-primary">{timeGroup}</div>
          <Button
            ref={drawerTriggerRef}
            className="filter-mobile-toggle"
            aria-label={`打开更多筛选，已选 ${selectedCount} 项`}
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            更多筛选{selectedCount ? ` · ${selectedCount}` : ''}
          </Button>
          <Drawer
            title="更多筛选"
            open={drawerOpen}
            size="100%"
            placement="right"
            rootClassName="filter-mobile-drawer"
            destroyOnHidden
            onClose={closeDrawer}
            extra={<span className="filter-drawer-count">已选 {selectedCount} 项</span>}
            footer={
              <Space.Compact block className="filter-drawer-actions">
                <Button block aria-label="重置全部筛选" onClick={reset}>
                  重置
                </Button>
                <Button block type="primary" aria-label="应用筛选" onClick={closeDrawer}>
                  应用
                </Button>
              </Space.Compact>
            }
          >
            {scopeGroup}
          </Drawer>
        </>
      ) : (
        <div className="filter-controls">
          <div className="filter-groups">
            {timeGroup}
            {scopeGroup}
          </div>
        </div>
      )}
    </section>
  )
}
