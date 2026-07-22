import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { downloadHourlyComparison, getHourlyComparisonDetails } from '@/api/client'
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

function Summary({ point }: { point: HourlySeriesPoint | null }) {
  if (!point) return null
  return (
    <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }} bordered>
      <Descriptions.Item label="当前ROI">{numeric(point.current.roi, 'ratio')}</Descriptions.Item>
      <Descriptions.Item label="目标ROI">{numeric(point.roi_target, 'ratio')}</Descriptions.Item>
      <Descriptions.Item label="当前消耗">
        {numeric(point.current.spend, 'currency')}
      </Descriptions.Item>
      <Descriptions.Item label="ROI涨幅">
        {numeric(point.comparison_result.roi_growth_percentage, 'percent')}
      </Descriptions.Item>
      <Descriptions.Item label="消耗涨幅">
        {numeric(point.comparison_result.spend_growth_percentage, 'percent')}
      </Descriptions.Item>
      <Descriptions.Item label="综合状态">
        <Tag
          color={
            point.status.level === 'positive'
              ? 'success'
              : point.status.level === 'critical'
                ? 'error'
                : 'default'
          }
        >
          {point.status.name}
        </Tag>
      </Descriptions.Item>
      <Descriptions.Item label="数据完整率">
        {point.current.coverage_rate === null
          ? '暂无排班基准'
          : numeric(Number(point.current.coverage_rate) * 100, 'percent')}
      </Descriptions.Item>
      <Descriptions.Item label="状态原因">
        {point.status.reasons.join('；') || '暂无'}
      </Descriptions.Item>
    </Descriptions>
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
    <Table<DetailRecord>
      size="small"
      rowKey={(row) =>
        row.id ?? `${row.period_type ?? ''}-${row.date ?? ''}-${row.room ?? ''}-${row.metric ?? ''}`
      }
      dataSource={rows}
      columns={columns}
      pagination={false}
      scroll={{ x: 'max-content', y: 440 }}
    />
  )
  return (
    <Drawer
      open={open}
      size="large"
      rootClassName="hourly-detail-drawer"
      title={`${hourLabel} 分时详情`}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Space wrap>
          <Button
            onClick={() =>
              void navigate(
                `/timeline?end=${request.endDate ?? ''}&rooms=${request.roomIds.join(',')}&hours=${hour ?? ''}`,
              )
            }
          >
            查看原小时趋势
          </Button>
          <Button onClick={() => void navigate('/alerts')}>查看相关预警</Button>
          <Button onClick={() => void downloadHourlyComparison(request)}>导出CSV</Button>
        </Space>
      }
    >
      {details.isLoading ? (
        <div className="hourly-drawer-loading">
          <Spin />
          <Typography.Text>加载分时详情…</Typography.Text>
        </div>
      ) : details.isError ? (
        <Alert
          type="error"
          showIcon
          title="分时详情加载失败"
          action={<Button onClick={() => void details.refetch()}>重试</Button>}
        />
      ) : details.data ? (
        <Space orientation="vertical" size={16} className="drawer-stack">
          <Summary point={details.data.summary[0] ?? null} />
          <Tabs
            items={[
              {
                key: 'date',
                label: '按日期',
                children: table(details.data.daily_rows, dailyColumns),
              },
              {
                key: 'room',
                label: '按直播间',
                children: table(details.data.room_rows, roomColumns),
              },
              {
                key: 'kline',
                label: '业务K线明细',
                children: table(details.data.kline_rows, klineColumns),
              },
              {
                key: 'raw',
                label: `原始记录 (${details.data.raw_total})`,
                children: (
                  <Table<DetailRecord>
                    size="small"
                    rowKey={(row) =>
                      row.id ?? `${row.date ?? ''}-${row.room ?? ''}-${row.period_type ?? 'raw'}`
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
                ),
              },
            ]}
          />
        </Space>
      ) : null}
    </Drawer>
  )
}
