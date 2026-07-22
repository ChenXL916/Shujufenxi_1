import { Button, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { HourlyMetricOption, HourlySeriesPoint } from '@/types/hourlyComparison'
import { formatMetric } from '@/utils/format'

function percent(value: string | number | null): string {
  if (value === null) return '—'
  return `${Number(value).toFixed(2)}%`
}

function statusColor(level: HourlySeriesPoint['status']['level']): string {
  return (
    {
      critical: 'error',
      warning: 'warning',
      positive: 'success',
      info: 'processing',
      improving: 'blue',
      normal: 'default',
      neutral: 'default',
    } as const
  )[level]
}

export function HourlyComparisonTable({
  points,
  metrics,
  selectedHour,
  onSelect,
  onDetails,
}: {
  points: HourlySeriesPoint[]
  metrics: HourlyMetricOption[]
  selectedHour: string | null
  onSelect: (hour: string) => void
  onDetails: (hour: string) => void
}) {
  const additionalMetricColumns: ColumnsType<HourlySeriesPoint> = metrics
    .filter((metric) => !['period_overall_roi', 'period_spend'].includes(metric.key))
    .flatMap((metric) => [
      {
        title: `${metric.name}（当前）`,
        width: 132,
        align: 'right' as const,
        render: (_: unknown, row: HourlySeriesPoint) =>
          formatMetric(row.current.metrics[metric.key] ?? null, metric.unit, metric.precision),
      },
      {
        title: `${metric.name}（基准）`,
        width: 132,
        align: 'right' as const,
        render: (_: unknown, row: HourlySeriesPoint) =>
          formatMetric(row.comparison?.metrics[metric.key] ?? null, metric.unit, metric.precision),
      },
    ])
  const columns: ColumnsType<HourlySeriesPoint> = [
    { title: '自然小时', dataIndex: 'hour', fixed: 'left', width: 92 },
    {
      title: '当前ROI',
      width: 96,
      align: 'right',
      render: (_, row) => formatMetric(row.current.roi, 'ratio'),
    },
    {
      title: '基准ROI',
      width: 96,
      align: 'right',
      render: (_, row) => formatMetric(row.comparison?.roi ?? null, 'ratio'),
    },
    {
      title: 'ROI涨幅',
      width: 100,
      align: 'right',
      render: (_, row) => percent(row.comparison_result.roi_growth_percentage),
    },
    {
      title: 'ROI目标',
      width: 92,
      align: 'right',
      render: (_, row) => formatMetric(row.roi_target, 'ratio'),
    },
    {
      title: '目标差',
      width: 92,
      align: 'right',
      render: (_, row) => formatMetric(row.comparison_result.roi_target_gap, 'ratio'),
    },
    {
      title: '是否达标',
      width: 92,
      render: (_, row) =>
        row.comparison_result.roi_target_reached === null ? (
          '—'
        ) : (
          <Tag color={row.comparison_result.roi_target_reached ? 'success' : 'warning'}>
            {row.comparison_result.roi_target_reached ? '达标' : '未达标'}
          </Tag>
        ),
    },
    {
      title: '当前消耗',
      width: 120,
      align: 'right',
      render: (_, row) => formatMetric(row.current.spend, 'currency'),
    },
    {
      title: '基准消耗',
      width: 120,
      align: 'right',
      render: (_, row) => formatMetric(row.comparison?.spend ?? null, 'currency'),
    },
    {
      title: '消耗涨幅',
      width: 100,
      align: 'right',
      render: (_, row) => percent(row.comparison_result.spend_growth_percentage),
    },
    ...additionalMetricColumns,
    ...(['open', 'close', 'high', 'low'] as const).map((field) => ({
      title: `ROI ${field}`,
      width: 92,
      align: 'right' as const,
      render: (_: unknown, row: HourlySeriesPoint) =>
        formatMetric(row.current.roi_ohlc?.[field] ?? null, 'ratio'),
    })),
    ...(['open', 'close', 'high', 'low'] as const).map((field) => ({
      title: `消耗 ${field}`,
      width: 110,
      align: 'right' as const,
      render: (_: unknown, row: HourlySeriesPoint) =>
        formatMetric(row.current.spend_ohlc?.[field] ?? null, 'currency'),
    })),
    {
      title: '综合状态',
      width: 138,
      render: (_, row) => (
        <Tooltip title={row.status.reasons.join('；') || '暂无判断原因'}>
          <Tag color={statusColor(row.status.level)}>{row.status.name}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '当前/基准样本',
      width: 130,
      align: 'right',
      render: (_, row) =>
        `${row.current.effective_samples}/${row.comparison?.effective_samples ?? '—'}`,
    },
    {
      title: '完整率',
      width: 92,
      align: 'right',
      render: (_, row) =>
        row.current.coverage_rate === null
          ? '暂无排班基准'
          : percent(Number(row.current.coverage_rate) * 100),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 82,
      render: (_, row) => (
        <Button
          type="link"
          aria-label={`查看 ${row.hour} 详情`}
          onClick={(event) => {
            event.stopPropagation()
            onDetails(row.hour)
          }}
        >
          详情
        </Button>
      ),
    },
  ]
  return (
    <Table<HourlySeriesPoint>
      rowKey="hour"
      size="small"
      pagination={false}
      sticky
      scroll={{ x: 2380 + additionalMetricColumns.length * 132, y: 520 }}
      dataSource={points}
      columns={columns}
      rowClassName={(row) => (row.hour === selectedHour ? 'hourly-row-selected' : '')}
      onRow={(row) => ({
        onClick: () => onSelect(row.hour),
        onKeyDown: (event) => {
          if (event.key === 'Enter') onSelect(row.hour)
          if (event.key === ' ') {
            event.preventDefault()
            onSelect(row.hour)
          }
        },
        tabIndex: 0,
        'aria-selected': row.hour === selectedHour,
      })}
    />
  )
}
