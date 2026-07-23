import {
  AimOutlined,
  BarChartOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  LineChartOutlined,
  NotificationOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Drawer, Table, Tabs } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { downloadHourlyComparison, getHourlyComparisonDetails } from '@/api/client'
import { ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import {
  DetailHero,
  DetailMetricGrid,
  DetailSectionHeading,
  type DetailStatus,
} from '@/features/detail-ui/DetailScaffold'
import type {
  HourlyComparisonRequest,
  HourlySeriesPoint,
  NumericValue,
} from '@/types/hourlyComparison'
import { formatMetric } from '@/utils/format'

interface DetailRecord extends Record<string, unknown> {
  id?: string
  date?: string
  room?: string
  metric?: string
  period_type?: string
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return `${value}`
  }
  return '—'
}

function numeric(value: NumericValue, unit: 'ratio' | 'currency' | 'percent'): string {
  if (unit === 'percent') {
    return value === null ? '—' : `${Number(value).toFixed(2)}%`
  }
  return formatMetric(value, unit)
}

const DIMENSION_LABELS: Record<HourlyComparisonRequest['seriesDimension'], string> = {
  summary: '整体汇总',
  room: '按直播间',
  anchor: '按主播',
  controller: '按场控',
  room_anchor: '直播间与主播',
}

const dailyColumns: ColumnsType<DetailRecord> = [
  { title: '周期', dataIndex: 'period_type', width: 90, render: valueText },
  { title: '日期', dataIndex: 'date', width: 110, render: valueText },
  { title: '直播间', dataIndex: 'room', width: 150, render: valueText },
  { title: '主播', dataIndex: 'anchor', width: 120, render: valueText },
  { title: '场控', dataIndex: 'controller', width: 120, render: valueText },
  { title: '计划主播', dataIndex: 'planned_anchor', width: 120, render: valueText },
  { title: '排班一致', dataIndex: 'schedule_match', width: 100, render: valueText },
  { title: '时段整体成交金额', dataIndex: 'period_overall_amount', width: 150, render: valueText },
  { title: '时段消耗', dataIndex: 'period_spend', width: 120, render: valueText },
  { title: '时段整体支付ROI', dataIndex: 'period_overall_roi', width: 140, render: valueText },
  { title: '时段成交订单数', dataIndex: 'period_order_count', width: 130, render: valueText },
  { title: '订单成本', dataIndex: 'period_overall_order_cost', width: 110, render: valueText },
  { title: 'ROI目标', dataIndex: 'roi_target', width: 90, render: valueText },
  { title: '是否达标', dataIndex: 'roi_target_reached', width: 90, render: valueText },
  { title: '数据状态', dataIndex: 'data_status', width: 100, render: valueText },
  { title: '最晚采集时间', dataIndex: 'latest_observed_at', width: 180, render: valueText },
]

const roomColumns: ColumnsType<DetailRecord> = [
  { title: '直播间', dataIndex: 'room', width: 150, render: valueText },
  { title: '产品品类', dataIndex: 'product_category', width: 100, render: valueText },
  { title: 'ROI目标', dataIndex: 'roi_target', width: 90, render: valueText },
  { title: '当前ROI', dataIndex: 'current_roi', width: 90, render: valueText },
  { title: '基准ROI', dataIndex: 'baseline_roi', width: 90, render: valueText },
  { title: 'ROI涨幅', dataIndex: 'roi_growth', width: 90, render: valueText },
  { title: '当前消耗', dataIndex: 'current_spend', width: 110, render: valueText },
  { title: '基准消耗', dataIndex: 'baseline_spend', width: 110, render: valueText },
  { title: '消耗涨幅', dataIndex: 'spend_growth', width: 90, render: valueText },
  { title: '综合状态', dataIndex: 'status', width: 130, render: valueText },
  { title: '有效天数', dataIndex: 'effective_days', width: 90, render: valueText },
  { title: '覆盖率', dataIndex: 'coverage_rate', width: 90, render: valueText },
]

const klineColumns: ColumnsType<DetailRecord> = [
  { title: '周期', dataIndex: 'period_type', width: 90, render: valueText },
  { title: '指标', dataIndex: 'metric', width: 100, render: valueText },
  ...(['open', 'close', 'high', 'low', 'average', 'median', 'total'] as const).map((field) => ({
    title: field,
    dataIndex: field,
    width: 100,
    render: valueText,
  })),
  { title: '首日', dataIndex: 'first_date', width: 110, render: valueText },
  { title: '末日', dataIndex: 'last_date', width: 110, render: valueText },
  { title: '最高日期', dataIndex: 'high_date', width: 110, render: valueText },
  { title: '最低日期', dataIndex: 'low_date', width: 110, render: valueText },
]

const rawColumns: ColumnsType<DetailRecord> = [
  { title: '完整采集时间', dataIndex: 'observed_at', width: 180, render: valueText },
  { title: '日期', dataIndex: 'business_date', width: 110, render: valueText },
  { title: '直播间', dataIndex: 'room', width: 150, render: valueText },
  { title: '自然小时', dataIndex: 'hour', width: 90, render: valueText },
  { title: '主播', dataIndex: 'anchor', width: 110, render: valueText },
  { title: '场控', dataIndex: 'controller', width: 110, render: valueText },
  { title: '有效', dataIndex: 'valid', width: 70, render: valueText },
  { title: '异常原因', dataIndex: 'invalid_reason', width: 180, render: valueText },
  { title: '原始字段', dataIndex: 'raw_payload', width: 320, ellipsis: true, render: valueText },
  { title: '更新时间', dataIndex: 'updated_at', width: 180, render: valueText },
]

function statusTone(point: HourlySeriesPoint): DetailStatus['tone'] {
  if (point.status.level === 'positive' || point.status.level === 'improving') return 'positive'
  if (point.status.level === 'critical') return 'negative'
  if (point.status.level === 'warning') return 'warning'
  if (point.status.level === 'info') return 'info'
  return 'neutral'
}

function Summary({
  point,
  hourLabel,
  request,
  dailyCount,
  rawCount,
}: {
  point: HourlySeriesPoint | null
  hourLabel: string
  request: HourlyComparisonRequest
  dailyCount: number
  rawCount: number
}) {
  if (!point) return null
  const targetStatus: DetailStatus =
    point.comparison_result.roi_target_reached === true
      ? { label: 'ROI 已达标', tone: 'positive' }
      : point.comparison_result.roi_target_reached === false
        ? { label: 'ROI 未达标', tone: 'negative' }
        : { label: '未配置达标结论', tone: 'neutral' }

  return (
    <>
      <DetailHero
        id="hourly-detail-title"
        icon={<ClockCircleOutlined />}
        iconTone="blue"
        eyebrow="HOURLY COMPARISON"
        title={`${hourLabel} 时段表现`}
        badge="周期对比"
        statuses={[{ label: point.status.name, tone: statusTone(point) }, targetStatus]}
        meta={`${dailyCount.toLocaleString('zh-CN')} 条日明细 · ${rawCount.toLocaleString('zh-CN')} 条原始记录`}
        contexts={[
          {
            key: 'hour',
            label: '自然小时',
            value: hourLabel,
            icon: <ClockCircleOutlined aria-hidden />,
          },
          {
            key: 'period-end',
            label: '当前周期截止',
            value: request.endDate ?? '最新完整日期',
            icon: <CalendarOutlined aria-hidden />,
          },
          {
            key: 'period-days',
            label: '统计周期',
            value: `${request.periodDays ?? 1} 天`,
            icon: <LineChartOutlined aria-hidden />,
          },
          {
            key: 'room-scope',
            label: '直播间范围',
            value: request.roomIds.length ? `${request.roomIds.length} 个直播间` : '全部授权直播间',
            icon: <DatabaseOutlined aria-hidden />,
          },
        ]}
        supplementary={[
          {
            key: 'aggregation',
            label: '统计口径',
            value: request.aggregationMode === 'sum' ? '周期汇总' : '按日平均',
          },
          {
            key: 'dimension',
            label: '拆分维度',
            value: DIMENSION_LABELS[request.seriesDimension],
          },
          {
            key: 'reason',
            label: '状态依据',
            value: point.status.reasons.join('；') || '当前时段没有额外异常说明',
          },
        ]}
      />

      <section className="detail-section" aria-labelledby="hourly-summary-title">
        <DetailSectionHeading
          id="hourly-summary-title"
          icon={<BarChartOutlined aria-hidden />}
          kicker="PERFORMANCE SUMMARY"
          title="核心表现"
          aside="当前周期与基准周期对比"
        />
        <DetailMetricGrid
          wide
          items={[
            {
              key: 'current-roi',
              label: '当前周期 ROI',
              value: numeric(point.current.roi, 'ratio'),
              hint: '当前',
            },
            {
              key: 'baseline-roi',
              label: '基准周期 ROI',
              value: numeric(point.comparison?.roi ?? null, 'ratio'),
              hint: '基准',
            },
            {
              key: 'roi-target',
              label: 'ROI 目标',
              value: numeric(point.roi_target, 'ratio'),
              hint: '目标',
              tone: targetStatus.tone,
            },
            {
              key: 'roi-growth',
              label: 'ROI 涨幅',
              value: numeric(point.comparison_result.roi_growth_percentage, 'percent'),
              hint: '较基准',
            },
            {
              key: 'current-spend',
              label: '当前周期消耗',
              value: numeric(point.current.spend, 'currency'),
              hint: '当前',
            },
            {
              key: 'baseline-spend',
              label: '基准周期消耗',
              value: numeric(point.comparison?.spend ?? null, 'currency'),
              hint: '基准',
            },
            {
              key: 'spend-growth',
              label: '消耗涨幅',
              value: numeric(point.comparison_result.spend_growth_percentage, 'percent'),
              hint: '较基准',
            },
            {
              key: 'coverage',
              label: '数据完整率',
              value:
                point.current.coverage_rate === null
                  ? '暂无排班基准'
                  : numeric(Number(point.current.coverage_rate) * 100, 'percent'),
              hint: '当前',
            },
          ]}
        />
      </section>
    </>
  )
}

export function HourlyDetailDrawer({
  open,
  hour,
  request,
  onClose,
}: {
  open: boolean
  hour: string | null
  request: HourlyComparisonRequest
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  useEffect(() => setPage(1), [hour])
  const details = useQuery({
    queryKey: ['hourly-comparison-details', request, hour, page],
    queryFn: () => getHourlyComparisonDetails(request, hour ?? '', page),
    enabled: open && Boolean(hour),
  })
  const hourLabel = hour ? `${hour.slice(0, 2)}:00-${hour.slice(3)}:00` : ''
  const table = (rows: Array<Record<string, unknown>>, columns: ColumnsType<DetailRecord>) => (
    <div className="detail-table-wrap">
      <Table<DetailRecord>
        size="small"
        rowKey={(row) =>
          row.id ??
          `${row.period_type ?? ''}-${row.date ?? ''}-${row.room ?? ''}-${row.metric ?? ''}`
        }
        dataSource={rows}
        columns={columns}
        pagination={false}
        scroll={{ x: 'max-content', y: 440 }}
      />
    </div>
  )
  return (
    <Drawer
      open={open}
      size="large"
      rootClassName="detail-drawer hourly-detail-drawer"
      title={`${hourLabel} 分时详情`}
      onClose={onClose}
      destroyOnHidden
    >
      {details.isLoading ? (
        <LoadingPanel />
      ) : details.isError ? (
        <ErrorPanel onRetry={() => void details.refetch()} />
      ) : details.data ? (
        <div className="detail-drawer-content">
          <Summary
            point={details.data.summary[0] ?? null}
            hourLabel={hourLabel}
            request={request}
            dailyCount={details.data.daily_rows.length}
            rawCount={details.data.raw_total}
          />

          <nav className="detail-action-bar" aria-label="分时详情操作">
            <Button
              icon={<LineChartOutlined />}
              onClick={() =>
                void navigate(
                  `/timeline?end=${request.endDate ?? ''}&rooms=${request.roomIds.join(',')}&hours=${hour ?? ''}`,
                )
              }
            >
              查看原小时趋势
            </Button>
            <Button icon={<NotificationOutlined />} onClick={() => void navigate('/alerts')}>
              查看相关预警
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => void downloadHourlyComparison(request)}
            >
              导出 CSV
            </Button>
          </nav>

          <section className="detail-section" aria-labelledby="hourly-facts-title">
            <DetailSectionHeading
              id="hourly-facts-title"
              icon={<AimOutlined aria-hidden />}
              kicker="SOURCE FACTS"
              title="明细数据"
              aside="按业务视角切换"
            />
            <Tabs
              className="detail-tabs"
              items={[
                {
                  key: 'date',
                  label: `按日期 (${details.data.daily_rows.length})`,
                  children: table(details.data.daily_rows, dailyColumns),
                },
                {
                  key: 'room',
                  label: `按直播间 (${details.data.room_rows.length})`,
                  children: table(details.data.room_rows, roomColumns),
                },
                {
                  key: 'kline',
                  label: `业务 K 线 (${details.data.kline_rows.length})`,
                  children: table(details.data.kline_rows, klineColumns),
                },
                {
                  key: 'raw',
                  label: `原始记录 (${details.data.raw_total})`,
                  children: (
                    <div className="detail-table-wrap">
                      <Table<DetailRecord>
                        size="small"
                        rowKey={(row) =>
                          row.id ??
                          `${row.date ?? ''}-${row.room ?? ''}-${row.period_type ?? 'raw'}`
                        }
                        dataSource={details.data.raw_records}
                        columns={rawColumns}
                        scroll={{ x: 'max-content', y: 440 }}
                        pagination={{
                          current: page,
                          pageSize: details.data.page_size,
                          total: details.data.raw_total,
                          showSizeChanger: false,
                          onChange: setPage,
                        }}
                      />
                    </div>
                  ),
                },
              ]}
            />
          </section>
        </div>
      ) : null}
    </Drawer>
  )
}
