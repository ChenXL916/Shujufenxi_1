import { useQuery } from '@tanstack/react-query'
import { Card, Col, Progress, Row, Space, Table, Tag, Typography } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getFilterOptions, getOverview } from '@/api/client'
import { FilterBar } from '@/components/FilterBar'
import { KpiCard } from '@/components/KpiCard'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { StatusBadge } from '@/components/StatusBadge'
import { HourlyRoiSpendSection } from '@/features/hourly-comparison/HourlyRoiSpendSection'
import { useDashboardFilters } from '@/hooks/useDashboardFilters'
import { formatMetric } from '@/utils/format'

export function OverviewPage() {
  const navigate = useNavigate()
  const [focusMetric, setFocusMetric] = useState<'roi' | 'spend' | null>(null)
  const { filters, update, reset } = useDashboardFilters()
  const options = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  const overview = useQuery({
    queryKey: ['overview', filters],
    queryFn: () => getOverview(filters),
    enabled: Boolean(filters.startDate),
    refetchInterval: 60_000,
  })
  const hasKpiData = overview.data?.kpis.some((item) => item.value !== null) ?? false
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader
        title="经营总览"
        description="根据所选周期、直播间、主播与场控查看核心经营表现；时段字段计算，累计指标取范围内最后有效点。"
        eyebrow="运营概览"
        actions={
          <Tag color={overview.data?.sync_mode === 'feishu' ? 'success' : 'processing'}>
            {overview.data?.sync_mode === 'feishu'
              ? '飞书实时源'
              : overview.data?.sync_mode === 'feishu_base_export'
                ? '飞书离线导出'
                : 'Excel 实际导出'}
          </Tag>
        }
      />
      <FilterBar
        options={options.data}
        filters={filters}
        update={update}
        reset={reset}
        showPeriodPresets
      />
      {overview.isLoading ? (
        <LoadingPanel />
      ) : overview.isError ? (
        <ErrorPanel onRetry={() => void overview.refetch()} />
      ) : !overview.data || !hasKpiData ? (
        <EmptyPanel />
      ) : (
        <>
          <section className="kpi-grid" aria-label="核心经营指标">
            {overview.data.kpis.map((item) => (
              <KpiCard
                key={item.metric_key}
                item={item}
                selected={
                  (focusMetric === 'roi' && item.metric_key === 'period_overall_roi') ||
                  (focusMetric === 'spend' && item.metric_key === 'period_spend')
                }
                onClick={() => {
                  if (item.metric_key === 'period_overall_roi') {
                    setFocusMetric('roi')
                    return
                  }
                  if (item.metric_key === 'period_spend') {
                    setFocusMetric('spend')
                    return
                  }
                  void navigate(
                    `/timeline?start=${filters.startDate ?? ''}&end=${filters.endDate ?? ''}&metrics=${item.metric_key}`,
                  )
                }}
              />
            ))}
          </section>
          <HourlyRoiSpendSection
            filters={filters}
            options={options.data}
            onGlobalFiltersChange={update}
            focusMetric={focusMetric}
            aside={
              <Space orientation="vertical" size={16} className="overview-insight-stack">
                <Card title="趋势与预警" className="data-card overview-insight-card">
                  <div className="overview-insight-list">
                    <div className="overview-insight-row">
                      <StatusBadge tone={overview.data.active_alerts > 0 ? 'warning' : 'positive'}>
                        活动预警
                      </StatusBadge>
                      <strong>{overview.data.active_alerts}</strong>
                    </div>
                    <div className="overview-insight-row">
                      <StatusBadge tone="info">数据同步</StatusBadge>
                      <strong>
                        {overview.data.sync_mode === 'feishu' ? '飞书实时源' : '本地数据源'}
                      </strong>
                    </div>
                    <div className="overview-insight-row">
                      <StatusBadge tone="neutral">T+1 检查</StatusBadge>
                      <strong>
                        次日 {String(overview.data.data_submission_deadline_hour).padStart(2, '0')}
                        :00
                      </strong>
                    </div>
                    <div className="overview-insight-row">
                      <StatusBadge tone="info">直播间覆盖</StatusBadge>
                      <strong>{overview.data.room_ranking.length}</strong>
                    </div>
                  </div>
                </Card>
                <Card title="数据与排班质量" className="data-card overview-insight-card">
                  <Space orientation="vertical" size={20} className="quality-panel">
                    <div>
                      <Typography.Text>数据完整率</Typography.Text>
                      {overview.data.data_completeness === null ? (
                        <Typography.Paragraph type="secondary">
                          待次日{' '}
                          {String(overview.data.data_submission_deadline_hour).padStart(2, '0')}
                          :00 补录
                        </Typography.Paragraph>
                      ) : (
                        <Progress
                          percent={Math.round(Number(overview.data.data_completeness) * 100)}
                          strokeColor="var(--color-accent-blue)"
                        />
                      )}
                    </div>
                    <div>
                      <Typography.Text>主播排班一致率</Typography.Text>
                      <Progress
                        percent={Math.round(Number(overview.data.anchor_match_rate ?? 0) * 100)}
                        strokeColor="var(--color-accent-orange)"
                      />
                    </div>
                    <div className="quality-row">
                      <span>当前预警</span>
                      <Tag color={overview.data.active_alerts ? 'error' : 'success'}>
                        {overview.data.active_alerts} 条
                      </Tag>
                    </div>
                  </Space>
                </Card>
              </Space>
            }
          />
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Card title="直播间表现" className="data-card">
                <Table
                  rowKey="room_id"
                  pagination={false}
                  scroll={{ x: 760 }}
                  dataSource={overview.data.room_ranking}
                  columns={[
                    { title: '直播间', dataIndex: 'room_name' },
                    { title: '有效小时', dataIndex: 'hours', align: 'right' },
                    {
                      title: '整体成交金额',
                      dataIndex: 'amount',
                      align: 'right',
                      render: (value: string | number | null) => formatMetric(value, 'currency'),
                    },
                    {
                      title: '汇总时段 ROI',
                      dataIndex: 'roi',
                      align: 'right',
                      render: (value: string | number | null) => formatMetric(value, 'ratio'),
                    },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}
    </Space>
  )
}
