import { useQuery } from '@tanstack/react-query'
import { Card, Space, Table } from 'antd'
import { getAnalysis, getFilterOptions } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import type { AnalysisRow } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

const copy = {
  anchors: ['主播分析', '排名至少结合有效小时与消耗门槛判断，不把短样本直接当成结论。'],
  controls: ['场控分析', '展示搭配表现与排班状态，不把相关关系表述为因果关系。'],
  pairings: ['主播 × 场控搭配', '用于寻找稳定搭配与异常时段，所有 ROI 按合计分子/消耗重算。'],
} as const

export function AnalysisPage({ dimension }: { dimension: 'anchors' | 'controls' | 'pairings' }) {
  const { filters, update, reset } = useDashboardFilters()
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  const analysis = useQuery({
    queryKey: ['analysis', dimension, filters],
    queryFn: () => getAnalysis(dimension, filters),
    enabled: Boolean(filters.startDate),
  })
  const [title, subtitle] = copy[dimension]
  const columns = [
    {
      title: dimension === 'anchors' ? '主播' : dimension === 'controls' ? '场控' : '主播 × 场控',
      dataIndex: 'name',
      fixed: 'left' as const,
      width: 180,
    },
    { title: '有效小时', dataIndex: 'valid_hours', align: 'right' as const, width: 100 },
    { title: '直播间数', dataIndex: 'room_count', align: 'right' as const, width: 100 },
    {
      title: '成交金额',
      dataIndex: 'period_overall_amount',
      align: 'right' as const,
      render: (value: AnalysisRow['period_overall_amount']) => formatMetric(value, 'currency'),
    },
    {
      title: '消耗',
      dataIndex: 'period_spend',
      align: 'right' as const,
      render: (value: AnalysisRow['period_spend']) => formatMetric(value, 'currency'),
    },
    {
      title: '汇总 ROI',
      dataIndex: 'period_overall_roi',
      align: 'right' as const,
      render: (value: AnalysisRow['period_overall_roi']) => formatMetric(value, 'ratio'),
    },
    {
      title: '订单数',
      dataIndex: 'period_order_count',
      align: 'right' as const,
      render: (value: AnalysisRow['period_order_count']) => formatMetric(value, 'count', 0),
    },
    {
      title: '订单成本',
      dataIndex: 'period_overall_order_cost',
      align: 'right' as const,
      render: (value: AnalysisRow['period_overall_order_cost']) => formatMetric(value, 'currency'),
    },
  ]
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader title={title} description={subtitle} eyebrow="PEOPLE PERFORMANCE" />
      <FilterBar options={options.data} filters={filters} update={update} reset={reset} />
      <Card className="data-card">
        {analysis.isLoading ? (
          <LoadingPanel />
        ) : analysis.isError ? (
          <ErrorPanel onRetry={() => void analysis.refetch()} />
        ) : !analysis.data?.length ? (
          <EmptyPanel />
        ) : (
          <Table<AnalysisRow>
            rowKey="key"
            sticky
            scroll={{ x: 1120, y: 620 }}
            pagination={{ pageSize: 20 }}
            dataSource={analysis.data}
            columns={columns}
          />
        )}
      </Card>
    </Space>
  )
}
