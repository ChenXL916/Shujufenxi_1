import { useQuery } from '@tanstack/react-query'
import { Card, Space, Table } from 'antd'
import { useMemo } from 'react'
import { getAnalysis, getFilterOptions } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import type { AnalysisRow } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

const DEFAULT_ANALYSIS_METRICS = [
  'period_overall_amount',
  'period_spend',
  'period_overall_roi',
  'period_net_roi',
  'period_order_count',
  'period_overall_order_cost',
  'period_viewers',
  'period_buyers',
] as const

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
  const selectedMetricKeys = useMemo(
    () => (filters.metricKeys.length ? filters.metricKeys : [...DEFAULT_ANALYSIS_METRICS]),
    [filters.metricKeys],
  )
  const selectedMetrics = useMemo(
    () =>
      selectedMetricKeys
        .map((key) => options.data?.metrics.find((metric) => metric.key === key))
        .filter((metric) => metric !== undefined),
    [options.data?.metrics, selectedMetricKeys],
  )
  const columns = useMemo(
    () => [
      {
        title: dimension === 'anchors' ? '主播' : dimension === 'controls' ? '场控' : '主播 × 场控',
        dataIndex: 'name',
        fixed: 'left' as const,
        width: 180,
      },
      { title: '有效小时', dataIndex: 'valid_hours', align: 'right' as const, width: 100 },
      { title: '直播间数', dataIndex: 'room_count', align: 'right' as const, width: 100 },
      ...selectedMetrics.map((metric) => ({
        title: metric.name,
        dataIndex: metric.key,
        align: 'right' as const,
        width: 150,
        render: (value: string | number | null) =>
          formatMetric(value, metric.unit, metric.precision),
      })),
    ],
    [dimension, selectedMetrics],
  )
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader title={title} description={subtitle} eyebrow="PEOPLE PERFORMANCE" />
      <FilterBar
        options={options.data}
        filters={filters}
        update={update}
        reset={reset}
        showMetrics
        showGrain={false}
        showPeriodPresets
      />
      <Card
        className="data-card"
        title={`${title}数据`}
        extra={`已选 ${selectedMetricKeys.length} 个指标`}
      >
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
            scroll={{ x: 380 + selectedMetrics.length * 150, y: 620 }}
            pagination={{ pageSize: 20 }}
            dataSource={analysis.data}
            columns={columns}
          />
        )}
      </Card>
    </Space>
  )
}
