import { useQuery } from '@tanstack/react-query'
import { Card, Segmented, Space, Table, Tag } from 'antd'
import { useEffect, useState } from 'react'
import { getComparisons, getFilterOptions } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import type { ComparisonRow } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

export function ComparisonPage() {
  const { filters, update, reset } = useDashboardFilters()
  const [comparisonType, setComparisonType] = useState('previous_day')
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  useEffect(() => {
    if (!filters.metricKeys.length && options.data) {
      update({
        metricKeys: options.data.metrics
          .filter((metric) => metric.default_visible)
          .slice(0, 4)
          .map((metric) => metric.key),
      })
    }
  }, [filters.metricKeys.length, options.data, update])
  const comparison = useQuery({
    queryKey: ['comparison', comparisonType, filters],
    queryFn: () => getComparisons(filters, comparisonType),
    enabled: Boolean(filters.startDate && filters.metricKeys.length),
  })
  const columns = [
    { title: '指标', dataIndex: 'name', fixed: 'left' as const, width: 200 },
    {
      title: '当前值',
      dataIndex: 'current_value',
      width: 140,
      align: 'right' as const,
      render: (value: ComparisonRow['current_value'], row: ComparisonRow) =>
        formatMetric(value, row.unit),
    },
    {
      title: '基准值',
      dataIndex: 'baseline_value',
      width: 140,
      align: 'right' as const,
      render: (value: ComparisonRow['baseline_value'], row: ComparisonRow) =>
        formatMetric(value, row.unit),
    },
    {
      title: '是基准的',
      dataIndex: 'ratio_percent',
      width: 120,
      align: 'right' as const,
      render: (value: ComparisonRow['ratio_percent']) =>
        value === null ? '—' : `${Number(value).toFixed(1)}%`,
    },
    {
      title: '增幅',
      dataIndex: 'growth_percent',
      width: 120,
      align: 'right' as const,
      render: (value: ComparisonRow['growth_percent']) =>
        value === null ? (
          '—'
        ) : (
          <Tag color={Number(value) >= 0 ? 'success' : 'error'}>
            {Number(value) >= 0 ? '+' : ''}
            {Number(value).toFixed(1)}%
          </Tag>
        ),
    },
    { title: '解释', dataIndex: 'explanation', width: 400 },
  ]
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader
        title="数据对比"
        description="同时展示“是基准的百分比”和“较基准增幅”，避免倍率与增长混淆"
        eyebrow="PERIOD COMPARISON"
        actions={
          <Segmented
            value={comparisonType}
            options={[
              { label: '今日/昨日', value: 'previous_day' },
              { label: '今日/上周', value: 'previous_week' },
              { label: '本月/上月', value: 'previous_month' },
            ]}
            onChange={setComparisonType}
          />
        }
      />
      <FilterBar
        options={options.data}
        filters={filters}
        update={update}
        reset={reset}
        showMetrics
      />
      <Card className="data-card">
        {comparison.isLoading ? (
          <LoadingPanel />
        ) : comparison.isError ? (
          <ErrorPanel onRetry={() => void comparison.refetch()} />
        ) : !comparison.data?.length ? (
          <EmptyPanel />
        ) : (
          <Table<ComparisonRow>
            rowKey="metric_key"
            pagination={false}
            dataSource={comparison.data}
            columns={columns}
            scroll={{ x: 1120 }}
          />
        )}
      </Card>
    </Space>
  )
}
