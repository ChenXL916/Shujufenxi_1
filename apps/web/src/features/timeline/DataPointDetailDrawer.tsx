import {
  BarChartOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  FieldTimeOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Collapse, Drawer, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useMemo } from 'react'
import { ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import {
  DetailHero,
  DetailMetricGrid,
  DetailSectionHeading,
  DetailStatusTag,
  type DetailStatus,
} from '@/features/detail-ui/DetailScaffold'
import type { DetailResponse, FilterOptions, Grain, MetricOption } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

const BASE_LABELS: Record<string, string> = {
  date: '业务日期',
  hour_slot: '自然小时',
  anchor: '实际主播',
  control: '场控',
  planned_anchor: '排班主播',
  anchor_match_status: '排班匹配',
  data_status: '数据状态',
  latest_observed_at: '最晚采集',
  observed_at: '采集时间',
  anchor_note: '主播备注',
  valid: '数据有效性',
  invalid_reason: '异常原因',
}

const PRIMARY_BASE_KEYS = new Set([
  'date',
  'hour_slot',
  'anchor',
  'control',
  'planned_anchor',
  'anchor_match_status',
  'data_status',
  'latest_observed_at',
  'observed_at',
  'valid',
])

const GROUP_META = {
  period: {
    title: '本时段表现',
    description: '当前自然小时内的增量与派生结果',
    className: 'period',
  },
  cumulative: {
    title: '直播累计',
    description: '截至当前采集点的累计结果',
    className: 'cumulative',
  },
  instant: {
    title: '实时快照',
    description: '当前采集时刻的即时状态',
    className: 'instant',
  },
  other: {
    title: '其他指标',
    description: '未归入上述口径的标准化结果',
    className: 'other',
  },
} as const

type MetricGroupKey = keyof typeof GROUP_META

interface MetricView {
  key: string
  value: string | number | null
  option?: MetricOption
}

interface DataPointDetailDrawerProps {
  detail?: DetailResponse
  filterOptions?: FilterOptions
  grain: Grain
  loading: boolean
  error: boolean
  open: boolean
  onClose: () => void
  onRetry: () => void
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未记录'
  if (typeof value === 'boolean') return value ? '有效' : '无效'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'bigint') return value.toString()
  return JSON.stringify(value) ?? '未记录'
}

function dateTimeText(value: unknown): string {
  if (typeof value !== 'string' || !value) return valueText(value)
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : value
}

function statusView(key: string, value: unknown): DetailStatus {
  const normalized =
    typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
      ? String(value).toLowerCase()
      : ''
  if (key === 'anchor_match_status') {
    const anchorStatuses: Record<string, DetailStatus> = {
      matched: { label: '排班一致', tone: 'positive' },
      mismatched: { label: '主播不一致', tone: 'negative' },
      scheduled_but_missing: { label: '排班待实绩', tone: 'warning' },
      no_schedule: { label: '未配置排班', tone: 'neutral' },
      off_air: { label: '排班停播', tone: 'neutral' },
      off_air_but_live: { label: '停播时段有实绩', tone: 'warning' },
    }
    return anchorStatuses[normalized] ?? { label: valueText(value), tone: 'neutral' }
  }
  if (key === 'data_status') {
    const dataStatuses: Record<string, DetailStatus> = {
      complete: { label: '数据完整', tone: 'positive' },
      partial: { label: '数据待补录', tone: 'warning' },
      missing: { label: '数据缺失', tone: 'negative' },
    }
    return dataStatuses[normalized] ?? { label: valueText(value), tone: 'neutral' }
  }
  if (key === 'valid') {
    return value === true || normalized === 'true'
      ? { label: '数据有效', tone: 'positive' }
      : { label: '数据异常', tone: 'negative' }
  }
  return { label: valueText(value), tone: 'neutral' }
}

function metricGroup(metric: MetricView): MetricGroupKey {
  if (metric.key.startsWith('period_')) return 'period'
  if (metric.option?.scope === 'cumulative' || metric.option?.is_cumulative) return 'cumulative'
  if (metric.option?.scope === 'instant') return 'instant'
  return 'other'
}

function scopeText(metric?: MetricOption): string {
  if (!metric) return '标准化'
  if (metric.scope === 'period') return '时段'
  if (metric.scope === 'cumulative') return '累计末值'
  if (metric.scope === 'instant') return '实时'
  if (metric.scope === 'derived') return '派生'
  return metric.scope
}

export function DataPointDetailDrawer({
  detail,
  filterOptions,
  grain,
  loading,
  error,
  open,
  onClose,
  onRetry,
}: DataPointDetailDrawerProps) {
  const metricGroups = useMemo(() => {
    const optionMap = new Map(filterOptions?.metrics.map((metric) => [metric.key, metric]))
    const optionOrder = new Map(filterOptions?.metrics.map((metric, index) => [metric.key, index]))
    const result: Record<MetricGroupKey, MetricView[]> = {
      period: [],
      cumulative: [],
      instant: [],
      other: [],
    }

    Object.entries(detail?.metrics ?? {})
      .map(([key, value]) => ({ key, value, option: optionMap.get(key) }))
      .sort(
        (left, right) =>
          (optionOrder.get(left.key) ?? Number.MAX_SAFE_INTEGER) -
            (optionOrder.get(right.key) ?? Number.MAX_SAFE_INTEGER) ||
          left.key.localeCompare(right.key),
      )
      .forEach((metric) => result[metricGroup(metric)].push(metric))

    return result
  }, [detail?.metrics, filterOptions?.metrics])

  const base = detail?.base ?? {}
  const date = valueText(base.date)
  const hourSlot = valueText(base.hour_slot)
  const anchor = valueText(base.anchor)
  const control = valueText(base.control)
  const plannedAnchor = valueText(base.planned_anchor)
  const observedAt = dateTimeText(base.observed_at ?? base.latest_observed_at)
  const matchStatus = statusView('anchor_match_status', base.anchor_match_status)
  const dataStatus =
    base.valid !== undefined
      ? statusView('valid', base.valid)
      : statusView('data_status', base.data_status)
  const extraBaseEntries = Object.entries(base).filter(
    ([key, value]) =>
      !PRIMARY_BASE_KEYS.has(key) && value !== null && value !== undefined && value !== '',
  )
  const metricCount = Object.keys(detail?.metrics ?? {}).length

  return (
    <Drawer
      size={760}
      open={open}
      onClose={onClose}
      destroyOnHidden
      rootClassName="detail-drawer timeline-detail-drawer"
      title="数据点详情"
    >
      {loading ? (
        <LoadingPanel />
      ) : error ? (
        <ErrorPanel onRetry={onRetry} />
      ) : (
        detail && (
          <div className="detail-drawer-content data-point-detail">
            <DetailHero
              id="detail-room-name"
              icon={<DatabaseOutlined />}
              eyebrow="LIVE DATA POINT"
              title={detail.room}
              badge={grain === 'hour' ? '自然小时汇总' : '真实采集点'}
              statuses={[
                dataStatus,
                ...(base.anchor_match_status !== undefined ? [matchStatus] : []),
              ]}
              meta={`${metricCount.toLocaleString('zh-CN')} 项标准化指标`}
              contexts={[
                {
                  key: 'date',
                  label: '业务日期',
                  value: date,
                  icon: <CalendarOutlined aria-hidden />,
                },
                {
                  key: 'hour',
                  label: '自然小时',
                  value: hourSlot,
                  icon: <ClockCircleOutlined aria-hidden />,
                },
                {
                  key: 'anchor',
                  label: '实际主播',
                  value: anchor,
                  icon: <UserOutlined aria-hidden />,
                },
                {
                  key: 'control',
                  label: '场控',
                  value: control,
                  icon: <TeamOutlined aria-hidden />,
                },
              ]}
              supplementary={[
                ...(base.planned_anchor !== undefined
                  ? [{ key: 'planned-anchor', label: '排班主播', value: plannedAnchor }]
                  : []),
                {
                  key: 'observed-at',
                  label: base.observed_at !== undefined ? '采集时间' : '最晚采集',
                  value: observedAt,
                },
                ...extraBaseEntries.map(([key, value]) => ({
                  key,
                  label: BASE_LABELS[key] ?? `扩展字段 · ${key}`,
                  value: key.includes('_at') ? dateTimeText(value) : valueText(value),
                })),
              ]}
            />

            <section className="detail-section" aria-labelledby="detail-metrics-title">
              <DetailSectionHeading
                id="detail-metrics-title"
                icon={<BarChartOutlined aria-hidden />}
                kicker="STANDARDIZED METRICS"
                title="标准化指标"
                aside="按数据口径分组"
              />

              <div className="detail-metric-groups">
                {(Object.keys(GROUP_META) as MetricGroupKey[]).map((groupKey) => {
                  const metrics = metricGroups[groupKey]
                  if (!metrics.length) return null
                  const meta = GROUP_META[groupKey]
                  return (
                    <section
                      className={`detail-metric-group ${meta.className}`}
                      key={groupKey}
                      aria-labelledby={`detail-metric-${groupKey}`}
                    >
                      <div className="detail-metric-group-heading">
                        <div>
                          <Typography.Title id={`detail-metric-${groupKey}`} level={5}>
                            {meta.title}
                          </Typography.Title>
                          <Typography.Text type="secondary">{meta.description}</Typography.Text>
                        </div>
                        <Tag>{metrics.length} 项</Tag>
                      </div>
                      <DetailMetricGrid
                        items={metrics.map((metric) => ({
                          key: metric.key,
                          label: metric.option?.name ?? metric.key,
                          hint: scopeText(metric.option),
                          value: formatMetric(
                            metric.value,
                            metric.option?.unit ?? 'ratio',
                            metric.option?.precision ?? 2,
                          ),
                        }))}
                      />
                    </section>
                  )
                })}
              </div>
            </section>

            {detail.points.length > 0 && (
              <section className="detail-section" aria-labelledby="detail-points-title">
                <DetailSectionHeading
                  id="detail-points-title"
                  icon={<FieldTimeOutlined aria-hidden />}
                  kicker="SOURCE POINTS"
                  title="采集记录"
                  aside={`${detail.points.length} 个采集点`}
                  compact
                />
                <div className="detail-point-list">
                  {detail.points.map((point, index) => {
                    const valid = point.valid !== false
                    const pointKey =
                      typeof point.id === 'string' || typeof point.id === 'number'
                        ? String(point.id)
                        : `point-${index}`
                    return (
                      <div className="detail-point-row" key={pointKey}>
                        <span className="detail-point-index">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <div>
                          <strong>{dateTimeText(point.observed_at)}</strong>
                          <small>
                            {point.invalid_reason
                              ? valueText(point.invalid_reason)
                              : '已纳入该小时标准化计算'}
                          </small>
                        </div>
                        <DetailStatusTag
                          status={{
                            label: valid ? '有效' : '异常',
                            tone: valid ? 'positive' : 'negative',
                          }}
                        />
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {detail.raw_payload && (
              <Collapse
                className="detail-raw-collapse"
                items={[
                  {
                    key: 'raw-payload',
                    label: (
                      <span className="detail-raw-label">
                        原始字段
                        <Tag>{Object.keys(detail.raw_payload).length} 项</Tag>
                      </span>
                    ),
                    children: (
                      <pre className="raw-json">{JSON.stringify(detail.raw_payload, null, 2)}</pre>
                    ),
                  },
                ]}
              />
            )}
          </div>
        )
      )}
    </Drawer>
  )
}
