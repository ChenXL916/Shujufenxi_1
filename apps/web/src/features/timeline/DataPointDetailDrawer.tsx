import {
  BarChartOutlined,
  CalendarOutlined,
  CheckCircleFilled,
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

interface StatusView {
  label: string
  tone: 'positive' | 'warning' | 'negative' | 'neutral'
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

function statusView(key: string, value: unknown): StatusView {
  const normalized =
    typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
      ? String(value).toLowerCase()
      : ''
  if (key === 'anchor_match_status') {
    const anchorStatuses: Record<string, StatusView> = {
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
    const dataStatuses: Record<string, StatusView> = {
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

function StatusTag({ status }: { status: StatusView }) {
  return (
    <Tag className={`detail-status-tag ${status.tone}`}>
      {status.tone === 'positive' && <CheckCircleFilled aria-hidden />}
      {status.label}
    </Tag>
  )
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
      rootClassName="timeline-detail-drawer"
      title="数据点详情"
    >
      {loading ? (
        <LoadingPanel />
      ) : error ? (
        <ErrorPanel onRetry={onRetry} />
      ) : (
        detail && (
          <div className="data-point-detail">
            <section className="detail-overview-card" aria-labelledby="detail-room-name">
              <div className="detail-overview-heading">
                <span className="detail-room-icon" aria-hidden>
                  <DatabaseOutlined />
                </span>
                <div className="detail-room-copy">
                  <Typography.Text className="detail-eyebrow">LIVE DATA POINT</Typography.Text>
                  <Typography.Title id="detail-room-name" level={3}>
                    {detail.room}
                  </Typography.Title>
                </div>
                <Tag className="detail-grain-tag">
                  {grain === 'hour' ? '自然小时汇总' : '真实采集点'}
                </Tag>
              </div>

              <div className="detail-status-row" aria-label="数据点状态">
                <StatusTag status={dataStatus} />
                {base.anchor_match_status !== undefined && <StatusTag status={matchStatus} />}
                <Typography.Text type="secondary">
                  {metricCount.toLocaleString('zh-CN')} 项标准化指标
                </Typography.Text>
              </div>

              <div className="detail-context-grid">
                <div className="detail-context-item">
                  <span>
                    <CalendarOutlined aria-hidden />
                    业务日期
                  </span>
                  <strong>{date}</strong>
                </div>
                <div className="detail-context-item">
                  <span>
                    <ClockCircleOutlined aria-hidden />
                    自然小时
                  </span>
                  <strong>{hourSlot}</strong>
                </div>
                <div className="detail-context-item">
                  <span>
                    <UserOutlined aria-hidden />
                    实际主播
                  </span>
                  <strong>{anchor}</strong>
                </div>
                <div className="detail-context-item">
                  <span>
                    <TeamOutlined aria-hidden />
                    场控
                  </span>
                  <strong>{control}</strong>
                </div>
              </div>

              <div className="detail-quality-grid">
                {base.planned_anchor !== undefined && (
                  <div>
                    <span>排班主播</span>
                    <strong>{plannedAnchor}</strong>
                  </div>
                )}
                <div>
                  <span>{base.observed_at !== undefined ? '采集时间' : '最晚采集'}</span>
                  <strong>{observedAt}</strong>
                </div>
                {extraBaseEntries.map(([key, value]) => (
                  <div key={key}>
                    <span>{BASE_LABELS[key] ?? `扩展字段 · ${key}`}</span>
                    <strong>{key.includes('_at') ? dateTimeText(value) : valueText(value)}</strong>
                  </div>
                ))}
              </div>
            </section>

            <section className="detail-section" aria-labelledby="detail-metrics-title">
              <div className="detail-section-heading">
                <div>
                  <Typography.Text className="detail-section-kicker">
                    <BarChartOutlined aria-hidden />
                    STANDARDIZED METRICS
                  </Typography.Text>
                  <Typography.Title id="detail-metrics-title" level={4}>
                    标准化指标
                  </Typography.Title>
                </div>
                <Typography.Text type="secondary">按数据口径分组</Typography.Text>
              </div>

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
                      <div className="detail-metric-grid">
                        {metrics.map((metric) => (
                          <article className="detail-metric-tile" key={metric.key}>
                            <div className="detail-metric-meta">
                              <span>{metric.option?.name ?? metric.key}</span>
                              <small>{scopeText(metric.option)}</small>
                            </div>
                            <strong
                              className="detail-metric-value"
                              aria-label={`${metric.option?.name ?? metric.key}：${formatMetric(
                                metric.value,
                                metric.option?.unit ?? 'ratio',
                                metric.option?.precision ?? 2,
                              )}`}
                            >
                              {formatMetric(
                                metric.value,
                                metric.option?.unit ?? 'ratio',
                                metric.option?.precision ?? 2,
                              )}
                            </strong>
                          </article>
                        ))}
                      </div>
                    </section>
                  )
                })}
              </div>
            </section>

            {detail.points.length > 0 && (
              <section className="detail-section" aria-labelledby="detail-points-title">
                <div className="detail-section-heading compact">
                  <div>
                    <Typography.Text className="detail-section-kicker">
                      <FieldTimeOutlined aria-hidden />
                      SOURCE POINTS
                    </Typography.Text>
                    <Typography.Title id="detail-points-title" level={4}>
                      采集记录
                    </Typography.Title>
                  </div>
                  <Tag>{detail.points.length} 个采集点</Tag>
                </div>
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
                        <StatusTag
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
