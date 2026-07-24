import { useQuery } from '@tanstack/react-query'
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import { Button, Card, Space, Table } from 'antd'
import { useCallback, useMemo, useState } from 'react'
import { getAnalysis, getAnchorHourDetails, getFilterOptions } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import type { AnalysisRow, AnchorHourDetailRow, DashboardFilters } from '@/types/dashboard'
import { formatMetric } from '@/utils/format'

const copy = {
  anchors: ['主播分析', '排名至少结合有效小时与消耗门槛判断，不把短样本直接当成结论。'],
  controls: ['场控分析', '展示搭配表现与排班状态，不把相关关系表述为因果关系。'],
  pairings: ['主播 × 场控搭配', '用于寻找稳定搭配与异常时段，所有 ROI 按合计分子/消耗重算。'],
} as const

type AnalysisSortOrder = 'ascend' | 'descend'
type AnalysisSortState = { key: string; order: AnalysisSortOrder } | null

function NumericSortHeader({
  label,
  columnKey,
  sort,
  onSort,
}: {
  label: string
  columnKey: string
  sort: AnalysisSortState
  onSort: (key: string, order: AnalysisSortOrder) => void
}) {
  return (
    <span className="analysis-sort-header">
      <span>{label}</span>
      <span className="analysis-sort-controls">
        <Button
          type="text"
          size="small"
          className={sort?.key === columnKey && sort.order === 'ascend' ? 'is-active' : ''}
          aria-label={`按${label}升序`}
          aria-pressed={sort?.key === columnKey && sort.order === 'ascend'}
          title={`按${label}升序`}
          icon={<ArrowUpOutlined />}
          onClick={(event) => {
            event.stopPropagation()
            onSort(columnKey, 'ascend')
          }}
        />
        <Button
          type="text"
          size="small"
          className={sort?.key === columnKey && sort.order === 'descend' ? 'is-active' : ''}
          aria-label={`按${label}降序`}
          aria-pressed={sort?.key === columnKey && sort.order === 'descend'}
          title={`按${label}降序`}
          icon={<ArrowDownOutlined />}
          onClick={(event) => {
            event.stopPropagation()
            onSort(columnKey, 'descend')
          }}
        />
      </span>
    </span>
  )
}

function sortNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

export function AnalysisPage({ dimension }: { dimension: 'anchors' | 'controls' | 'pairings' }) {
  const { filters, update, reset } = useDashboardFilters()
  const [detailPage, setDetailPage] = useState(1)
  const [detailPageSize, setDetailPageSize] = useState(50)
  const [sort, setSort] = useState<AnalysisSortState>(null)
  const updateFilters = useCallback(
    (patch: Partial<DashboardFilters>) => {
      setDetailPage(1)
      update(patch)
    },
    [update],
  )
  const resetFilters = useCallback(() => {
    setDetailPage(1)
    reset()
  }, [reset])
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  const defaultMetricKeys = useMemo(
    () =>
      options.data?.metrics.filter((metric) => metric.analysis_default).map(({ key }) => key) ?? [],
    [options.data?.metrics],
  )
  const selectedMetricKeys = useMemo(
    () => (filters.metricKeys.length ? filters.metricKeys : defaultMetricKeys),
    [defaultMetricKeys, filters.metricKeys],
  )
  const analysisFilters = useMemo(
    () => ({ ...filters, metricKeys: selectedMetricKeys }),
    [filters, selectedMetricKeys],
  )
  const analysis = useQuery({
    queryKey: ['analysis', dimension, analysisFilters],
    queryFn: () => getAnalysis(dimension, analysisFilters),
    enabled: Boolean(options.data && filters.startDate),
  })
  const anchorHours = useQuery({
    queryKey: ['anchor-hours', analysisFilters, detailPage, detailPageSize],
    queryFn: () => getAnchorHourDetails(analysisFilters, detailPage, detailPageSize),
    enabled: dimension === 'anchors' && Boolean(options.data && filters.startDate),
  })
  const [title, subtitle] = copy[dimension]
  const selectedMetrics = useMemo(
    () =>
      selectedMetricKeys
        .map((key) => options.data?.metrics.find((metric) => metric.key === key))
        .filter((metric) => metric !== undefined),
    [options.data?.metrics, selectedMetricKeys],
  )
  const sortBy = useCallback((key: string, order: AnalysisSortOrder) => {
    setSort({ key, order })
  }, [])
  const sortedAnalysis = useMemo(() => {
    if (!analysis.data || !sort) return analysis.data ?? []
    return [...analysis.data].sort((left, right) => {
      const leftValue = sortNumber(left[sort.key])
      const rightValue = sortNumber(right[sort.key])
      if (leftValue === null && rightValue === null) return 0
      if (leftValue === null) return 1
      if (rightValue === null) return -1
      return sort.order === 'ascend' ? leftValue - rightValue : rightValue - leftValue
    })
  }, [analysis.data, sort])
  const columns = useMemo(
    () => [
      {
        title: dimension === 'anchors' ? '主播' : dimension === 'controls' ? '场控' : '主播 × 场控',
        dataIndex: 'name',
        fixed: 'left' as const,
        width: 180,
        render: (value: string) =>
          dimension === 'anchors' ? (
            <Button
              type="link"
              className="anchor-summary-action"
              aria-label={`查看${value}的全部时段数据`}
              title={`查看${value}的全部时段数据`}
              onClick={() => updateFilters({ anchors: [value] })}
            >
              {value}
            </Button>
          ) : (
            value
          ),
      },
      {
        title: (
          <NumericSortHeader label="有效小时" columnKey="valid_hours" sort={sort} onSort={sortBy} />
        ),
        dataIndex: 'valid_hours',
        align: 'right' as const,
        width: 132,
      },
      {
        title: (
          <NumericSortHeader label="直播间数" columnKey="room_count" sort={sort} onSort={sortBy} />
        ),
        dataIndex: 'room_count',
        align: 'right' as const,
        width: 132,
      },
      ...(dimension === 'anchors'
        ? [
            {
              title: (
                <NumericSortHeader
                  label="时均成交"
                  columnKey="hourly_average_amount"
                  sort={sort}
                  onSort={sortBy}
                />
              ),
              dataIndex: 'hourly_average_amount',
              align: 'right' as const,
              width: 166,
              render: (value: string | number | null) => formatMetric(value, 'currency', 2),
            },
          ]
        : []),
      ...selectedMetrics.map((metric) => ({
        title: (
          <NumericSortHeader
            label={`${metric.name}${metric.aggregation === 'NONE' ? '（最近时段）' : ''}`}
            columnKey={metric.key}
            sort={sort}
            onSort={sortBy}
          />
        ),
        dataIndex: metric.key,
        align: 'right' as const,
        width: 150,
        render: (value: string | number | null) =>
          formatMetric(value, metric.unit, metric.precision),
      })),
    ],
    [dimension, selectedMetrics, sort, sortBy, updateFilters],
  )
  const anchorHourColumns = useMemo(
    () => [
      {
        title: '日期',
        dataIndex: 'business_date',
        fixed: 'left' as const,
        width: 112,
      },
      {
        title: '自然小时',
        dataIndex: 'hour_slot',
        fixed: 'left' as const,
        width: 96,
      },
      { title: '直播间', dataIndex: 'room_name', width: 160 },
      { title: '主播', dataIndex: 'anchor_name', width: 150 },
      {
        title: '场控',
        dataIndex: 'control_name',
        width: 120,
        render: (value: string | null) => value ?? '—',
      },
      ...selectedMetrics.map((metric) => ({
        title: metric.name,
        key: metric.key,
        align: 'right' as const,
        width: 150,
        render: (_: unknown, row: AnchorHourDetailRow) =>
          formatMetric(row.metrics[metric.key] ?? null, metric.unit, metric.precision),
      })),
    ],
    [selectedMetrics],
  )
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader title={title} description={subtitle} eyebrow="PEOPLE PERFORMANCE" />
      <FilterBar
        options={options.data}
        filters={analysisFilters}
        update={updateFilters}
        reset={resetFilters}
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
            scroll={{
              x: 444 + (dimension === 'anchors' ? 166 : 0) + selectedMetrics.length * 150,
              y: 620,
            }}
            pagination={{ pageSize: 20 }}
            dataSource={sortedAnalysis}
            columns={columns}
          />
        )}
      </Card>
      {dimension === 'anchors' ? (
        <Card
          className="data-card"
          title="主播时段明细"
          extra={
            anchorHours.data
              ? `当前筛选范围共 ${anchorHours.data.total} 条时段数据`
              : '按当前筛选加载全部时段'
          }
        >
          {anchorHours.isLoading ? (
            <LoadingPanel />
          ) : anchorHours.isError ? (
            <ErrorPanel onRetry={() => void anchorHours.refetch()} />
          ) : !anchorHours.data?.items.length ? (
            <EmptyPanel />
          ) : (
            <Table<AnchorHourDetailRow>
              rowKey="key"
              sticky
              scroll={{ x: 638 + selectedMetrics.length * 150, y: 620 }}
              dataSource={anchorHours.data.items}
              columns={anchorHourColumns}
              pagination={{
                current: detailPage,
                pageSize: detailPageSize,
                total: anchorHours.data.total,
                showSizeChanger: true,
                pageSizeOptions: [20, 50, 100, 200],
                showTotal: (total) => `共 ${total} 条时段数据`,
                onChange: (page, pageSize) => {
                  setDetailPage(pageSize === detailPageSize ? page : 1)
                  setDetailPageSize(pageSize)
                },
              }}
            />
          )}
        </Card>
      ) : null}
    </Space>
  )
}
