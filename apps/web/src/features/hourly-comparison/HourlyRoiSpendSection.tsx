import {
  DownOutlined,
  DownloadOutlined,
  ExpandOutlined,
  FileImageOutlined,
  ReloadOutlined,
  SettingOutlined,
  UpOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Divider,
  Modal,
  Segmented,
  Select,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd'
import dayjs from 'dayjs'
import type { EChartsType } from 'echarts/core'
import type { ReactNode } from 'react'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { downloadHourlyComparison, getHourlyComparison } from '@/api/client'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { chartSemanticColors } from '@/theme/chartTheme'
import type { DashboardFilters, FilterOptions } from '@/types/dashboard'
import type {
  HourlyAggregationMode,
  HourlyChartType,
  HourlyComparisonRequest,
  HourlySeriesDimension,
} from '@/types/hourlyComparison'
import { HourlyAdditionalMetricChart } from './HourlyAdditionalMetricChart'
import { HourlyComparisonTable } from './HourlyComparisonTable'
import { HourlyDetailDrawer } from './HourlyDetailDrawer'
import { HourlyRoiSpendChart } from './HourlyRoiSpendChart'

const PERIOD_OPTIONS = [
  { label: '1天', value: 1 },
  { label: '3天', value: 3 },
  { label: '5天', value: 5 },
  { label: '7天', value: 7 },
  { label: '15天', value: 15 },
  { label: '30天', value: 30 },
  { label: '自定义', value: 'custom' },
] as const

const CORE_METRIC_IDS = ['period_overall_roi', 'period_spend'] as const

function selectedMetricIds(value: string | null): string[] {
  const requested = value?.split(',').filter(Boolean) ?? []
  return [...new Set([...CORE_METRIC_IDS, ...requested])].slice(0, 4)
}

type PeriodPreset = 1 | 3 | 5 | 7 | 15 | 30 | 'custom'
const PRESET_DAYS = [1, 3, 5, 7, 15, 30] as const

function periodPreset(value: string | null): PeriodPreset {
  if (value === 'custom') return 'custom'
  const numeric = Number(value)
  return PRESET_DAYS.includes(numeric as (typeof PRESET_DAYS)[number])
    ? (numeric as Exclude<PeriodPreset, 'custom'>)
    : 7
}

function inheritedPeriodPreset(startDate?: string, endDate?: string): PeriodPreset {
  if (!startDate || !endDate) return 7
  const days = dayjs(endDate).diff(dayjs(startDate), 'day') + 1
  return PRESET_DAYS.includes(days as (typeof PRESET_DAYS)[number])
    ? (days as Exclude<PeriodPreset, 'custom'>)
    : 'custom'
}

function chartType(value: string | null): HourlyChartType {
  return value === 'business_kline' || value === 'bar' ? value : 'line'
}

function aggregationMode(value: string | null): HourlyAggregationMode {
  return value === 'daily_average' ? 'daily_average' : 'sum'
}

function seriesDimension(value: string | null): HourlySeriesDimension {
  return value === 'room' || value === 'anchor' || value === 'controller' ? value : 'summary'
}

function boolParam(value: string | null, fallback: boolean): boolean {
  if (value === null) return fallback
  return value === '1' || value === 'true'
}

export function HourlyRoiSpendSection({
  filters,
  options,
  onGlobalFiltersChange,
  focusMetric,
  aside,
}: {
  filters: DashboardFilters
  options?: FilterOptions
  onGlobalFiltersChange: (patch: Partial<DashboardFilters>) => void
  focusMetric: 'roi' | 'spend' | null
  aside?: ReactNode
}) {
  const sectionRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<EChartsType | null>(null)
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)')
  const advancedControlsId = useId()
  const [search, setSearch] = useSearchParams()
  const [period, setPeriod] = useState<PeriodPreset>(() =>
    search.has('hc_period')
      ? periodPreset(search.get('hc_period'))
      : inheritedPeriodPreset(filters.startDate, filters.endDate),
  )
  const [endDate, setEndDate] = useState(
    () => search.get('hc_end') ?? filters.endDate ?? options?.max_date ?? undefined,
  )
  const [customStart, setCustomStart] = useState(
    () => search.get('hc_start') ?? filters.startDate ?? undefined,
  )
  const [customEnd, setCustomEnd] = useState(
    () => search.get('hc_custom_end') ?? filters.endDate ?? undefined,
  )
  const [compareEnabled, setCompareEnabled] = useState(() =>
    boolParam(search.get('hc_compare'), true),
  )
  const [aggregation, setAggregation] = useState<HourlyAggregationMode>(() =>
    aggregationMode(search.get('hc_aggregation')),
  )
  const [type, setType] = useState<HourlyChartType>(() => chartType(search.get('hc_chart')))
  const [dimension, setDimension] = useState<HourlySeriesDimension>(() =>
    seriesDimension(search.get('hc_dimension')),
  )
  const [includeToday, setIncludeToday] = useState(() => boolParam(search.get('hc_today'), false))
  const [showRangeBand, setShowRangeBand] = useState(() => boolParam(search.get('hc_range'), false))
  const [showAllLabels, setShowAllLabels] = useState(false)
  const [metricIds, setMetricIds] = useState<string[]>(() =>
    selectedMetricIds(search.get('hc_metrics')),
  )
  const [selectedHour, setSelectedHour] = useState<string | null>(null)
  const [drawerHour, setDrawerHour] = useState<string | null>(null)
  const [activeSeriesKey, setActiveSeriesKey] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [toolbarExpanded, setToolbarExpanded] = useState(() =>
    boolParam(search.get('hc_range'), false),
  )

  const updateUrlPatch = useCallback(
    (patch: Record<string, string | number | boolean | null | undefined>) => {
      const next = new URLSearchParams(search)
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === undefined || value === '') next.delete(key)
        else next.set(key, typeof value === 'boolean' ? (value ? '1' : '0') : String(value))
      }
      setSearch(next, { replace: true })
    },
    [search, setSearch],
  )
  const updateUrl = useCallback(
    (key: string, value: string | number | boolean | null | undefined) => {
      updateUrlPatch({ [key]: value })
    },
    [updateUrlPatch],
  )

  useEffect(() => {
    if (!search.has('hc_end') && filters.endDate) setEndDate(filters.endDate)
  }, [filters.endDate, search])

  useEffect(() => {
    if ([...search.keys()].some((key) => key.startsWith('hc_'))) return
    setPeriod(inheritedPeriodPreset(filters.startDate, filters.endDate))
    setEndDate(filters.endDate ?? options?.max_date ?? undefined)
    setCustomStart(filters.startDate)
    setCustomEnd(filters.endDate)
    setCompareEnabled(true)
    setAggregation('sum')
    setType('line')
    setDimension('summary')
    setIncludeToday(false)
    setShowRangeBand(false)
    setMetricIds([...CORE_METRIC_IDS])
  }, [filters.endDate, filters.startDate, options?.max_date, search])

  useEffect(() => {
    if (!focusMetric) return
    sectionRef.current?.scrollIntoView({
      behavior: reducedMotion ? 'auto' : 'smooth',
      block: 'start',
    })
  }, [focusMetric, reducedMotion])

  const request = useMemo<HourlyComparisonRequest>(
    () => ({
      endDate: period === 'custom' ? customEnd : endDate,
      periodDays: period === 'custom' ? undefined : period,
      customStartDate: period === 'custom' ? customStart : undefined,
      customEndDate: period === 'custom' ? customEnd : undefined,
      compareEnabled,
      aggregationMode: aggregation,
      chartType: type,
      metricIds,
      roomIds: filters.roomIds,
      anchorNames: filters.anchors,
      anchorMembers: filters.anchorMembers,
      controlNames: filters.controls,
      naturalHours: filters.hours,
      seriesDimension: dimension,
      includeToday,
      includeInProgress: true,
      showRangeBand,
    }),
    [
      aggregation,
      compareEnabled,
      customEnd,
      customStart,
      dimension,
      endDate,
      filters.anchorMembers,
      filters.anchors,
      filters.controls,
      filters.hours,
      filters.roomIds,
      includeToday,
      metricIds,
      period,
      showRangeBand,
      type,
    ],
  )

  const comparison = useQuery({
    queryKey: ['hourly-comparison', request],
    queryFn: () => getHourlyComparison(request),
    refetchInterval: includeToday ? 60_000 : false,
    placeholderData: undefined,
  })

  useEffect(() => {
    const first = comparison.data?.series[0]
    if (!first) return
    setActiveSeriesKey((current) =>
      comparison.data?.series.some((item) => item.series_key === current)
        ? current
        : first.series_key,
    )
  }, [comparison.data])

  useEffect(() => {
    const summary = comparison.data?.series[0]
    if (dimension === 'summary' && filters.roomIds.length > 1 && summary?.multiple_targets) {
      setDimension('room')
      updateUrl('hc_dimension', 'room')
      void message.info('所选直播间ROI目标不同，已自动按直播间拆分')
    }
  }, [comparison.data, dimension, filters.roomIds.length, updateUrl])

  const activeSeries =
    comparison.data?.series.find((item) => item.series_key === activeSeriesKey) ??
    comparison.data?.series[0]
  const selectedMetrics =
    comparison.data?.metrics.filter((metric) => metricIds.includes(metric.key)) ?? []
  const additionalMetrics = selectedMetrics.filter(
    (metric) => !CORE_METRIC_IDS.includes(metric.key as (typeof CORE_METRIC_IDS)[number]),
  )
  const hasValues = Boolean(
    comparison.data?.series.some((series) =>
      series.points.some((point) => point.current.roi !== null || point.current.spend !== null),
    ),
  )

  const setPeriodValue = (value: string | number) => {
    const next = value === 'custom' ? 'custom' : periodPreset(String(value))
    setPeriod(next)
    updateUrl('hc_period', next)
  }

  const resetSection = () => {
    setPeriod(7)
    setEndDate(filters.endDate ?? options?.max_date ?? undefined)
    setCustomStart(filters.startDate)
    setCustomEnd(filters.endDate)
    setCompareEnabled(true)
    setAggregation('sum')
    setType('line')
    setDimension('summary')
    setIncludeToday(false)
    setShowRangeBand(false)
    setShowAllLabels(false)
    setMetricIds([...CORE_METRIC_IDS])
    setSelectedHour(null)
    setToolbarExpanded(false)
    const next = new URLSearchParams(search)
    for (const key of [...next.keys()]) if (key.startsWith('hc_')) next.delete(key)
    setSearch(next, { replace: true })
  }

  const exportImage = () => {
    const instance = chartInstance.current
    if (!instance || !comparison.data) return
    const anchor = document.createElement('a')
    anchor.href = instance.getDataURL({
      type: 'png',
      pixelRatio: 2,
      backgroundColor: chartSemanticColors.canvas,
    })
    anchor.download = `24小时ROI消耗对比_${comparison.data.current_period.start}_${comparison.data.current_period.end}.png`
    anchor.click()
  }

  const toolbar = (
    <div className="hourly-toolbar" aria-label="24小时周期对比工具栏">
      <div className="hourly-toolbar-row period-scroll">
        <Typography.Text strong>周期</Typography.Text>
        <Segmented value={period} options={[...PERIOD_OPTIONS]} onChange={setPeriodValue} />
        {period === 'custom' ? (
          <DatePicker.RangePicker
            value={customStart && customEnd ? [dayjs(customStart), dayjs(customEnd)] : null}
            onChange={(_, dates) => {
              const [start, end] = dates
              setCustomStart(start || undefined)
              setCustomEnd(end || undefined)
              updateUrlPatch({ hc_start: start || null, hc_custom_end: end || null })
            }}
          />
        ) : (
          <DatePicker
            aria-label="24小时对比截止日期"
            value={endDate ? dayjs(endDate) : null}
            onChange={(_, value) => {
              setEndDate(value || undefined)
              updateUrl('hc_end', value || null)
            }}
          />
        )}
        <Typography.Text>上一周期对比</Typography.Text>
        <Switch
          aria-label="上一周期对比"
          checked={compareEnabled}
          onChange={(value) => {
            setCompareEnabled(value)
            updateUrl('hc_compare', value ? null : false)
          }}
        />
        <Typography.Text>包含今日实时数据</Typography.Text>
        <Switch
          aria-label="包含今日实时数据"
          checked={includeToday}
          onChange={(value) => {
            setIncludeToday(value)
            const nextEnd = value ? dayjs().format('YYYY-MM-DD') : options?.max_date
            setEndDate(nextEnd ?? undefined)
            updateUrlPatch({ hc_today: value || null, hc_end: nextEnd })
          }}
        />
      </div>
      <div className="hourly-toolbar-row">
        <Typography.Text strong>口径</Typography.Text>
        <Segmented
          value={aggregation}
          options={[
            { label: '合计', value: 'sum' },
            { label: '日均', value: 'daily_average' },
          ]}
          onChange={(value) => {
            const next = aggregationMode(String(value))
            setAggregation(next)
            if (next === 'sum' && showRangeBand) {
              setShowRangeBand(false)
              updateUrlPatch({ hc_aggregation: null, hc_range: null })
            } else {
              updateUrl('hc_aggregation', next === 'sum' ? null : next)
            }
          }}
        />
        <Typography.Text strong>图表</Typography.Text>
        <Segmented
          value={type}
          options={[
            { label: '周期对比折线', value: 'line' },
            { label: '业务K线', value: 'business_kline' },
            { label: '柱状图', value: 'bar' },
          ]}
          onChange={(value) => {
            const next = chartType(String(value))
            setType(next)
            updateUrl('hc_chart', next === 'line' ? null : next)
          }}
        />
        <Typography.Text strong>拆分</Typography.Text>
        <Select<HourlySeriesDimension>
          aria-label="24小时图表拆分方式"
          className="hourly-dimension-select"
          popupMatchSelectWidth={144}
          value={dimension}
          options={[
            { label: '汇总', value: 'summary' },
            { label: '按直播间', value: 'room' },
            { label: '按主播', value: 'anchor' },
            { label: '按场控', value: 'controller' },
          ]}
          onChange={(value) => {
            setDimension(value)
            updateUrl('hc_dimension', value === 'summary' ? null : value)
          }}
        />
        <Select
          mode="multiple"
          aria-label="24小时图表直播间"
          placeholder="全部授权直播间"
          value={filters.roomIds}
          maxTagCount="responsive"
          className="hourly-room-select"
          options={options?.rooms.map((room) => ({ label: room.name, value: room.id }))}
          onChange={(roomIds) => onGlobalFiltersChange({ roomIds })}
        />
        <Select
          mode="multiple"
          aria-label="24小时指标"
          value={metricIds}
          maxCount={4}
          maxTagCount={1}
          maxTagPlaceholder={(omitted) => `+${omitted.length} 项`}
          optionFilterProp="label"
          className="hourly-metric-select"
          options={comparison.data?.metrics.map((metric) => ({
            label: metric.name,
            value: metric.key,
            disabled: CORE_METRIC_IDS.includes(metric.key as (typeof CORE_METRIC_IDS)[number]),
          }))}
          onChange={(values) => {
            const next = selectedMetricIds(values.join(','))
            setMetricIds(next)
            updateUrl('hc_metrics', next.length > CORE_METRIC_IDS.length ? next.join(',') : null)
          }}
        />
      </div>
      <div className="hourly-toolbar-footer">
        <div className="hourly-toolbar-quick-actions">
          <Button icon={<ReloadOutlined />} onClick={() => void comparison.refetch()}>
            刷新
          </Button>
          <Button icon={<ExpandOutlined />} onClick={() => setFullscreen(true)}>
            全屏
          </Button>
        </div>
        <Button
          type="text"
          className="hourly-toolbar-more"
          icon={<SettingOutlined />}
          aria-controls={advancedControlsId}
          aria-expanded={toolbarExpanded}
          onClick={() => setToolbarExpanded((value) => !value)}
        >
          更多设置与导出 {toolbarExpanded ? <UpOutlined /> : <DownOutlined />}
        </Button>
      </div>
      {toolbarExpanded ? (
        <div id={advancedControlsId} className="hourly-toolbar-advanced">
          <div className="hourly-display-options">
            <div className="hourly-toggle-option">
              <Typography.Text>周期波动区间</Typography.Text>
              <Switch
                aria-label="周期波动区间"
                checked={showRangeBand}
                onChange={(value) => {
                  if (value && aggregation === 'sum') {
                    setAggregation('daily_average')
                    void message.info('波动区间与日均同量级，已自动切换为日均口径')
                  }
                  setShowRangeBand(value)
                  updateUrlPatch({
                    ...(value && aggregation === 'sum' ? { hc_aggregation: 'daily_average' } : {}),
                    hc_range: value || null,
                  })
                }}
              />
            </div>
            <div className="hourly-toggle-option">
              <Typography.Text>全部数据标签</Typography.Text>
              <Switch
                aria-label="全部数据标签"
                checked={showAllLabels}
                onChange={setShowAllLabels}
              />
            </div>
          </div>
          <div className="hourly-export-actions">
            <Button icon={<FileImageOutlined />} disabled={!comparison.data} onClick={exportImage}>
              导出图片
            </Button>
            <Button
              icon={<DownloadOutlined />}
              disabled={!comparison.data}
              onClick={() => void downloadHourlyComparison(request)}
            >
              导出数据
            </Button>
            <Button onClick={resetSection}>重置本区域</Button>
          </div>
        </div>
      ) : null}
    </div>
  )

  return (
    <div ref={sectionRef} id="hourly-roi-spend" className="hourly-comparison-section">
      <div className={aside ? 'hourly-primary-grid' : undefined}>
        <Card
          className="hourly-comparison-card"
          title={
            <Space wrap>
              <span>24小时ROI与消耗周期对比</span>
              {focusMetric ? (
                <Tag color="processing">当前聚焦：{focusMetric === 'roi' ? 'ROI' : '消耗'}</Tag>
              ) : null}
            </Space>
          }
          extra={
            comparison.data ? (
              <Typography.Text type="secondary">
                数据更新至 {comparison.data.meta.data_updated_at ?? '暂无有效采集时间'}
              </Typography.Text>
            ) : null
          }
        >
          {toolbar}
          <Divider />
          {comparison.isLoading ? (
            <Skeleton active paragraph={{ rows: 12 }} />
          ) : comparison.isError ? (
            <Alert
              type="error"
              showIcon
              title="24小时周期对比加载失败"
              description="原经营总览仍可继续使用，请重试本区域。"
              action={
                <Button aria-label="重试24小时数据" onClick={() => void comparison.refetch()}>
                  重试
                </Button>
              }
            />
          ) : !comparison.data?.series.length ? (
            <Alert
              type="info"
              showIcon
              title="当前筛选条件下暂无有效小时数据，请调整日期、直播间、主播或场控。"
            />
          ) : (
            <Space orientation="vertical" size={16} className="hourly-content">
              <Space wrap className="hourly-summary-tags">
                <Tag color="blue">
                  当前：{comparison.data.current_period.start} 至{' '}
                  {comparison.data.current_period.end}
                </Tag>
                <Tag>
                  对比：
                  {comparison.data.comparison_period
                    ? `${comparison.data.comparison_period.start} 至 ${comparison.data.comparison_period.end}`
                    : '已关闭'}
                </Tag>
                {activeSeries?.roi_target !== null ? (
                  <Tag color="gold">ROI目标 {Number(activeSeries?.roi_target).toFixed(2)}</Tag>
                ) : (
                  <Tag>当前直播间未配置ROI目标</Tag>
                )}
                {!hasValues ? <Tag color="warning">当前范围只有排班或无有效实绩</Tag> : null}
                {activeSeries?.target_message ? (
                  <Tag color="warning">{activeSeries.target_message}</Tag>
                ) : null}
                <Tag color="green">真实小时事实 · 缺失不补0</Tag>
                <Typography.Text type="secondary">ROI按成交金额合计÷消耗合计重算</Typography.Text>
                {comparison.data.series.length > 1 ? (
                  <Select
                    value={activeSeries?.series_key}
                    options={comparison.data.series.map((item) => ({
                      label: item.series_name,
                      value: item.series_key,
                    }))}
                    onChange={setActiveSeriesKey}
                  />
                ) : null}
              </Space>
              {comparison.data.meta.series_dimension === 'room' &&
              comparison.data.series.length > 1 ? (
                <div className="hourly-room-small-multiples">
                  {comparison.data.series.map((roomSeries) => (
                    <Card
                      key={roomSeries.series_key}
                      size="small"
                      title={roomSeries.series_name}
                      extra={
                        roomSeries.roi_target === null ? (
                          <Tag>未配置ROI目标</Tag>
                        ) : (
                          <Tag color="gold">ROI目标 {Number(roomSeries.roi_target).toFixed(2)}</Tag>
                        )
                      }
                    >
                      <HourlyRoiSpendChart
                        data={{ ...comparison.data, series: [roomSeries] }}
                        chartType={type}
                        selectedHour={selectedHour}
                        showAllLabels={showAllLabels}
                        activeSeriesKey={roomSeries.series_key}
                        showRangeBand={
                          showRangeBand && aggregation === 'daily_average' && type === 'line'
                        }
                        onChartReady={(chart) => {
                          if (roomSeries.series_key === activeSeries?.series_key) {
                            chartInstance.current = chart
                          }
                        }}
                        onHourClick={(hour) => {
                          setActiveSeriesKey(roomSeries.series_key)
                          setSelectedHour(hour)
                          setDrawerHour(hour)
                        }}
                      />
                    </Card>
                  ))}
                </div>
              ) : (
                <HourlyRoiSpendChart
                  data={comparison.data}
                  chartType={type}
                  selectedHour={selectedHour}
                  showAllLabels={showAllLabels}
                  activeSeriesKey={activeSeries?.series_key ?? null}
                  showRangeBand={
                    showRangeBand && aggregation === 'daily_average' && type === 'line'
                  }
                  onChartReady={(chart) => {
                    chartInstance.current = chart
                  }}
                  onHourClick={(hour) => {
                    setSelectedHour(hour)
                    setDrawerHour(hour)
                  }}
                />
              )}
              {additionalMetrics.length && activeSeries ? (
                <div className="hourly-additional-metrics">
                  <Typography.Title level={5}>
                    已选附加指标 · {activeSeries.series_name}
                  </Typography.Title>
                  <div className="hourly-additional-metric-grid">
                    {additionalMetrics.map((metric) => (
                      <Card
                        key={metric.key}
                        size="small"
                        title={`${metric.name}（${metric.unit}）`}
                        extra={<Tag color="green">数据库小时值</Tag>}
                      >
                        <HourlyAdditionalMetricChart
                          data={{ ...comparison.data, series: [activeSeries] }}
                          metric={metric}
                          chartType={type}
                          selectedHour={selectedHour}
                          showAllLabels={showAllLabels}
                          onHourClick={(hour) => {
                            setSelectedHour(hour)
                            setDrawerHour(hour)
                          }}
                        />
                      </Card>
                    ))}
                  </div>
                </div>
              ) : null}
            </Space>
          )}
        </Card>
        {aside ? (
          <aside className="hourly-comparison-aside" aria-label="趋势与预警摘要">
            {aside}
          </aside>
        ) : null}
      </div>

      {comparison.data && activeSeries ? (
        <Card
          className="hourly-comparison-table-card"
          title="24小时ROI与消耗对比明细"
          extra={<Typography.Text type="secondary">固定24行；点击行联动图表</Typography.Text>}
        >
          <HourlyComparisonTable
            points={activeSeries.points}
            metrics={selectedMetrics}
            selectedHour={selectedHour}
            onSelect={setSelectedHour}
            onDetails={(hour) => {
              setSelectedHour(hour)
              setDrawerHour(hour)
            }}
          />
        </Card>
      ) : null}

      <Modal
        open={fullscreen}
        width="96vw"
        footer={null}
        title="24小时ROI与消耗周期对比（全屏）"
        onCancel={() => setFullscreen(false)}
        destroyOnHidden
      >
        {comparison.data ? (
          <HourlyRoiSpendChart
            data={
              comparison.data.meta.series_dimension === 'room' && activeSeries
                ? { ...comparison.data, series: [activeSeries] }
                : comparison.data
            }
            chartType={type}
            selectedHour={selectedHour}
            showAllLabels={showAllLabels}
            activeSeriesKey={activeSeries?.series_key ?? null}
            showRangeBand={showRangeBand && aggregation === 'daily_average' && type === 'line'}
            onHourClick={(hour) => {
              setSelectedHour(hour)
              setDrawerHour(hour)
            }}
          />
        ) : null}
      </Modal>

      <HourlyDetailDrawer
        open={Boolean(drawerHour)}
        hour={drawerHour}
        request={request}
        onClose={() => setDrawerHour(null)}
      />
    </div>
  )
}
