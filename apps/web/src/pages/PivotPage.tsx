import { DownloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Space, Table } from 'antd'
import { downloadExport, getFilterOptions, getPivot } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import type { PivotNode } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

export function PivotPage() {
  const { filters, update, reset } = useDashboardFilters()
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  const pivot = useQuery({
    queryKey: ['pivot', filters],
    queryFn: () => getPivot(filters),
    enabled: Boolean(filters.startDate),
  })
  const columns = [
    {
      title: '主播 / 场控 / 日期 / 自然小时',
      dataIndex: 'label',
      key: 'label',
      fixed: 'left' as const,
      width: 260,
    },
    { title: '有效小时', dataIndex: 'valid_hours', align: 'right' as const, width: 100 },
    {
      title: '时段整体成交金额',
      dataIndex: 'period_overall_amount',
      align: 'right' as const,
      width: 170,
      render: (value: PivotNode['period_overall_amount']) => formatMetric(value, 'currency'),
    },
    {
      title: '时段消耗',
      dataIndex: 'period_spend',
      align: 'right' as const,
      width: 140,
      render: (value: PivotNode['period_spend']) => formatMetric(value, 'currency'),
    },
    {
      title: '汇总时段整体支付 ROI',
      dataIndex: 'period_overall_roi',
      align: 'right' as const,
      width: 190,
      render: (value: PivotNode['period_overall_roi']) => formatMetric(value, 'ratio'),
    },
    {
      title: '时段成交订单数',
      dataIndex: 'period_order_count',
      align: 'right' as const,
      width: 150,
      render: (value: PivotNode['period_order_count']) => formatMetric(value, 'count', 0),
    },
    {
      title: '汇总时段订单成本',
      dataIndex: 'period_overall_order_cost',
      align: 'right' as const,
      width: 180,
      render: (value: PivotNode['period_overall_order_cost']) => formatMetric(value, 'currency'),
    },
  ]
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader
        title="主播场控时间汇总透视表"
        description="主播 → 场控 → 日期 → 自然小时；固定关键列，指标在表格内部横向滚动。"
        eyebrow="ANCHOR × CONTROLLER PIVOT"
        actions={
          <Space>
            <Button icon={<DownloadOutlined />} onClick={() => void downloadExport(filters, 'csv')}>
              CSV
            </Button>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={() => void downloadExport(filters, 'xlsx')}
            >
              XLSX
            </Button>
          </Space>
        }
      />
      <FilterBar options={options.data} filters={filters} update={update} reset={reset} />
      <Card className="pivot-card">
        {pivot.isLoading ? (
          <LoadingPanel />
        ) : pivot.isError ? (
          <ErrorPanel onRetry={() => void pivot.refetch()} />
        ) : !pivot.data?.length ? (
          <EmptyPanel />
        ) : (
          <Table<PivotNode>
            rowKey="key"
            sticky
            defaultExpandAllRows
            pagination={false}
            scroll={{ x: 1300, y: 700 }}
            dataSource={pivot.data}
            columns={columns}
          />
        )}
      </Card>
    </Space>
  )
}
