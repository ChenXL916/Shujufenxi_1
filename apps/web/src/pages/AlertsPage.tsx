import {
  ExperimentOutlined,
  EyeOutlined,
  ReloadOutlined,
  SendOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Result,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  acknowledgeAlert,
  evaluateAlerts,
  getAlertEvents,
  getAnchorTrendEvent,
  getAnchorTrends,
  getCurrentUser,
  getFilterOptions,
  recalculateAnchorTrends,
  retryAlertPush,
  sendAnchorTrendSummary,
  testAnchorTrendPush,
} from '@/api/client'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { PageHeader } from '@/components/PageHeader'
import type {
  AnchorTrendFilters,
  AnchorTrendItem,
  AnchorTrendItemDetails,
  AnchorTrendNotificationType,
  AnchorTrendPeriodDays,
  AnchorTrendRawRecord,
  AnchorTrendType,
  RoiTargetStatus,
} from '@/types/anchorTrends'
import type { AlertEvent, FilterOptions } from '@/types/dashboard'
import { formatMetric, formatRoiChange } from '@/utils/format'

type TrendTab = AnchorTrendType | 'events'

interface TrendViewState {
  tab: TrendTab
  period_days: AnchorTrendPeriodDays
  end_date?: string
  room_ids: string[]
  anchor_names: string[]
  control_names: string[]
  roi_target_status?: RoiTargetStatus
  minimum_coverage_rate?: number
  pushed?: boolean
}

interface DetailSelection {
  eventId: string
  itemId: string
  anchorName: string
}

interface ForceResendForm {
  reason: string
}

const PERIODS: AnchorTrendPeriodDays[] = [1, 3, 5, 7, 15, 30]
const TAB_KEYS = new Set<TrendTab>(['rise', 'fall', 'insufficient', 'events'])
const severity = {
  info: { label: '提示', color: 'blue' },
  warning: { label: '警告', color: 'orange' },
  critical: { label: '严重', color: 'red' },
}

function splitSearchValue(value: string | null): string[] {
  return (
    value
      ?.split(',')
      .map((item) => item.trim())
      .filter(Boolean) ?? []
  )
}

function forbidden(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number } }).response?.status === 403
  )
}

function mutationError(error: unknown, fallback: string): string {
  if (typeof error !== 'object' || error === null || !('response' in error)) return fallback
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)
    const handleChange = (event: MediaQueryListEvent) => setMatches(event.matches)
    setMatches(mediaQuery.matches)
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [query])

  return matches
}

function useTrendViewState() {
  const [search, setSearch] = useSearchParams()
  const state = useMemo<TrendViewState>(() => {
    const requestedTab = search.get('tab') as TrendTab | null
    const requestedPeriod = Number(search.get('period_days') ?? 3)
    const coverage = Number(search.get('minimum_coverage_rate'))
    const pushedValue = search.get('pushed')
    const targetValue = search.get('roi_target_status')
    return {
      tab: requestedTab && TAB_KEYS.has(requestedTab) ? requestedTab : 'rise',
      period_days: PERIODS.includes(requestedPeriod as AnchorTrendPeriodDays)
        ? (requestedPeriod as AnchorTrendPeriodDays)
        : 3,
      end_date: search.get('end_date') ?? undefined,
      room_ids: splitSearchValue(search.get('room_ids')),
      anchor_names: splitSearchValue(search.get('anchor_names')),
      control_names: splitSearchValue(search.get('control_names')),
      roi_target_status:
        targetValue === 'reached' || targetValue === 'not_reached' ? targetValue : undefined,
      minimum_coverage_rate:
        Number.isFinite(coverage) && coverage >= 0 && coverage <= 1 ? coverage : undefined,
      pushed: pushedValue === 'true' ? true : pushedValue === 'false' ? false : undefined,
    }
  }, [search])

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(search)
    Object.entries(patch).forEach(([key, value]) => {
      if (value === null || value === '') next.delete(key)
      else next.set(key, value)
    })
    setSearch(next, { replace: true })
  }

  const reset = () => setSearch({ tab: 'rise', period_days: '3' }, { replace: true })
  return { state, update, reset }
}

export function AlertsPage() {
  const queryClient = useQueryClient()
  const { state, update, reset } = useTrendViewState()
  const [detail, setDetail] = useState<DetailSelection | null>(null)
  const [forceOpen, setForceOpen] = useState(false)
  const [forceForm] = Form.useForm<ForceResendForm>()
  const isTrendTab = state.tab !== 'events'

  const user = useQuery({ queryKey: ['current-user'], queryFn: getCurrentUser, staleTime: 60_000 })
  const options = useQuery({
    queryKey: ['filter-options'],
    queryFn: getFilterOptions,
    staleTime: 60_000,
  })
  const trendFilters = useMemo<AnchorTrendFilters>(
    () => ({
      period_days: state.period_days,
      end_date: state.end_date,
      room_ids: state.room_ids,
      anchor_names: state.anchor_names,
      control_names: state.control_names,
      trend_type: 'all',
      roi_target_status: state.roi_target_status,
      minimum_coverage_rate: state.minimum_coverage_rate,
      pushed: state.pushed,
    }),
    [state],
  )
  const trends = useQuery({
    queryKey: ['anchor-trends', trendFilters],
    queryFn: () => getAnchorTrends(trendFilters),
    enabled: isTrendTab,
  })

  const currentNotificationType: AnchorTrendNotificationType | null =
    state.tab === 'rise'
      ? 'anchor_rise_summary'
      : state.tab === 'fall'
        ? 'anchor_fall_summary'
        : null
  const currentEvent = trends.data?.events.find(
    (event) => event.notification_type === currentNotificationType,
  )
  const canManageAlerts =
    user.data?.can_manage_alerts ?? user.data?.features?.can_manage_alerts ?? false
  const canRecalculate =
    canManageAlerts || user.data?.role === 'admin' || user.data?.role === 'operator'
  const isAdmin = canManageAlerts || user.data?.role === 'admin'

  const refreshTrends = async () => {
    await queryClient.invalidateQueries({ queryKey: ['anchor-trends'] })
  }
  const recalculate = useMutation({
    mutationFn: () =>
      recalculateAnchorTrends({
        ...(currentEvent?.rule_id ? { rule_id: currentEvent.rule_id } : {}),
        period_days: state.period_days,
        ...(state.end_date ? { end_date: state.end_date } : {}),
        room_ids: state.room_ids,
        anchor_names: state.anchor_names,
      }),
    onSuccess: async () => {
      await refreshTrends()
      void message.success('主播趋势已按当前筛选重算')
    },
    onError: (error) => void message.error(mutationError(error, '重算失败，请检查规则与数据周期')),
  })
  const testPush = useMutation({
    mutationFn: () => {
      if (!currentNotificationType) throw new Error('当前页签不支持测试推送')
      return testAnchorTrendPush({ notification_type: currentNotificationType })
    },
    onSuccess: (result) =>
      void message.success(
        result.push_status === 'sent' ? '趋势测试消息已发送' : 'Mock 测试卡片已生成',
      ),
    onError: (error) => void message.error(mutationError(error, '测试推送失败')),
  })
  const send = useMutation({
    mutationFn: (values: { force: boolean; reason?: string }) => {
      if (!currentEvent || !currentNotificationType) throw new Error('当前榜单尚无可发送事件')
      return sendAnchorTrendSummary({
        rule_id: currentEvent.rule_id,
        period: currentEvent.current_period_end,
        notification_type: currentNotificationType,
        force_resend: values.force,
        ...(values.reason ? { resend_reason: values.reason } : {}),
      })
    },
    onSuccess: async (_, variables) => {
      if (variables.force) {
        forceForm.resetFields()
        setForceOpen(false)
      }
      await refreshTrends()
      void message.success(variables.force ? '榜单已按原因强制重发' : '榜单发送任务已完成')
    },
    onError: (error) => void message.error(mutationError(error, '发送失败，请检查规则与推送状态')),
  })

  const rows =
    state.tab === 'rise'
      ? (trends.data?.rise ?? [])
      : state.tab === 'fall'
        ? (trends.data?.fall ?? [])
        : state.tab === 'insufficient'
          ? (trends.data?.insufficient ?? [])
          : []
  const summary = trends.data?.summary
  const tabItems = [
    { key: 'rise', label: `主播上涨榜${summary ? ` ${summary.rise_count}` : ''}` },
    { key: 'fall', label: `主播下跌榜${summary ? ` ${summary.fall_count}` : ''}` },
    {
      key: 'insufficient',
      label: `样本不足${summary ? ` ${summary.insufficient_count}` : ''}`,
    },
    { key: 'events', label: '历史预警（按需查看）' },
  ]

  return (
    <Space orientation="vertical" size={16} className="page-stack anchor-trend-page">
      <PageHeader
        title="主播趋势预警中心"
        description="对比等长完整自然日，ROI 始终按成交金额合计 ÷ 消耗合计重算；默认不展示数据质量告警。"
        eyebrow="INCIDENT & TREND MONITORING"
        actions={
          <Space wrap>
            {user.isError ? <Tag color="warning">权限信息加载失败，操作已隐藏</Tag> : null}
            {isTrendTab && canRecalculate ? (
              <Button
                icon={<SyncOutlined />}
                aria-label="重算当前趋势"
                loading={recalculate.isPending}
                onClick={() => recalculate.mutate()}
              >
                重算当前趋势
              </Button>
            ) : null}
            {isTrendTab && isAdmin && currentNotificationType ? (
              <Button
                icon={<ExperimentOutlined />}
                aria-label={`测试${state.tab === 'rise' ? '上涨' : '下跌'}榜推送`}
                loading={testPush.isPending}
                onClick={() => testPush.mutate()}
              >
                测试{state.tab === 'rise' ? '上涨' : '下跌'}榜推送
              </Button>
            ) : null}
            {isTrendTab && isAdmin && currentNotificationType ? (
              <Button
                type="primary"
                icon={<SendOutlined />}
                aria-label={`发送当前${state.tab === 'rise' ? '上涨' : '下跌'}榜`}
                disabled={!currentEvent || currentEvent.push_status === 'sent'}
                loading={send.isPending}
                onClick={() => send.mutate({ force: false })}
              >
                发送当前{state.tab === 'rise' ? '上涨' : '下跌'}榜
              </Button>
            ) : null}
            {isTrendTab && isAdmin && currentNotificationType ? (
              <Button
                danger
                aria-label={`强制重发当前${state.tab === 'rise' ? '上涨' : '下跌'}榜`}
                disabled={!currentEvent}
                onClick={() => setForceOpen(true)}
              >
                强制重发当前{state.tab === 'rise' ? '上涨' : '下跌'}榜
              </Button>
            ) : null}
          </Space>
        }
      />

      <Alert
        type="info"
        showIcon
        title="趋势榜只使用已存储的完整小时事实；样本不足单独列示且不会发送到业务群。"
        description="运营可按授权房间重算；测试、正式发送和强制重发仅管理员可用。历史预警页签需显式打开，因此数据质量事件不会干扰默认榜单。"
      />

      <TrendFilterBar
        state={state}
        options={options.data}
        optionsLoading={options.isLoading}
        optionsError={options.isError}
        onRetryOptions={() => void options.refetch()}
        update={update}
        reset={reset}
      />

      <Card className="data-card anchor-trend-card">
        <Tabs
          activeKey={state.tab}
          items={tabItems}
          onChange={(tab) => update({ tab })}
          aria-label="预警中心榜单"
        />
        {state.tab === 'events' ? (
          <LegacyAlertsPanel canOperate={canRecalculate} />
        ) : trends.isLoading ? (
          <LoadingPanel />
        ) : trends.isError && forbidden(trends.error) ? (
          <Result
            status="403"
            title="暂无主播趋势预警查看权限"
            subTitle="请联系管理员开通直播间或预警中心权限。"
          />
        ) : trends.isError ? (
          <ErrorPanel onRetry={() => void trends.refetch()} />
        ) : (
          <Space orientation="vertical" size={16} className="drawer-stack">
            <PeriodSummary
              current={trends.data?.current_period ?? null}
              baseline={trends.data?.baseline_period ?? null}
            />
            <TrendSummaryCards summary={summary} />
            {state.tab !== 'insufficient' && (summary?.insufficient_count ?? 0) > 0 ? (
              <Alert
                type="warning"
                showIcon
                title={`另有 ${summary?.insufficient_count ?? 0} 位主播样本不足，未进入上涨或下跌榜。`}
                description="可打开“样本不足”页签查看完整率、有效小时与未入榜原因。"
                action={
                  <Button onClick={() => update({ tab: 'insufficient' })}>查看样本不足</Button>
                }
              />
            ) : null}
            {rows.length ? (
              <TrendTable
                rows={rows}
                trendType={state.tab}
                onOpenDetail={(item) =>
                  setDetail({
                    eventId: item.event_id,
                    itemId: item.item_id,
                    anchorName: item.anchor_name,
                  })
                }
              />
            ) : (
              <Empty
                description={
                  state.tab === 'insufficient'
                    ? '当前筛选条件下没有样本不足主播。'
                    : `当前筛选条件下暂无主播${state.tab === 'rise' ? '上涨' : '下跌'}结果，可调整周期或由运营重新计算。`
                }
              />
            )}
          </Space>
        )}
      </Card>

      <TrendDetailDrawer selection={detail} onClose={() => setDetail(null)} />
      <Modal
        open={forceOpen}
        title={`强制重发当前${state.tab === 'rise' ? '上涨' : '下跌'}榜`}
        okText="确认强制重发"
        cancelText="取消"
        confirmLoading={send.isPending}
        destroyOnHidden
        onCancel={() => {
          forceForm.resetFields()
          setForceOpen(false)
        }}
        onOk={() => void forceForm.submit()}
      >
        <Alert
          type="warning"
          showIcon
          title="强制重发会创建新的审计事件，不能绕过去重而不留原因。"
          className="anchor-trend-modal-alert"
        />
        <Form<ForceResendForm>
          form={forceForm}
          layout="vertical"
          onFinish={({ reason }) => send.mutate({ force: true, reason: reason.trim() })}
        >
          <Form.Item
            label="强制重发原因"
            name="reason"
            rules={[{ required: true, whitespace: true, message: '请填写强制重发原因' }]}
          >
            <Input.TextArea
              rows={4}
              maxLength={1000}
              showCount
              placeholder="例如：修正统计口径后，需要向运营群同步更正榜单"
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}

function TrendFilterBar({
  state,
  options,
  optionsLoading,
  optionsError,
  onRetryOptions,
  update,
  reset,
}: {
  state: TrendViewState
  options?: FilterOptions
  optionsLoading: boolean
  optionsError: boolean
  onRetryOptions: () => void
  update: (patch: Record<string, string | null>) => void
  reset: () => void
}) {
  return (
    <section className="filter-bar anchor-trend-filters" aria-label="主播趋势筛选">
      <Space orientation="vertical" size={10} className="drawer-stack">
        <Space wrap size={[10, 10]}>
          <Segmented
            aria-label="统计周期"
            value={state.period_days}
            options={PERIODS.map((period) => ({ label: `${period}天`, value: period }))}
            onChange={(period) => update({ period_days: String(period) })}
          />
          <DatePicker
            aria-label="趋势截止日期"
            placeholder="截止日期（默认最新）"
            allowClear
            value={state.end_date ? dayjs(state.end_date) : null}
            onChange={(value) => update({ end_date: value?.format('YYYY-MM-DD') ?? null })}
          />
          <Select
            mode="multiple"
            showSearch
            maxTagCount="responsive"
            aria-label="趋势直播间"
            placeholder="直播间"
            loading={optionsLoading}
            value={state.room_ids}
            options={options?.rooms.map((room) => ({ label: room.name, value: room.id }))}
            onChange={(values) => update({ room_ids: values.length ? values.join(',') : null })}
            className="filter-select"
          />
          <Select
            mode="multiple"
            showSearch
            maxTagCount="responsive"
            aria-label="趋势主播"
            placeholder="主播"
            loading={optionsLoading}
            value={state.anchor_names}
            options={options?.anchors.map((name) => ({ label: name, value: name }))}
            onChange={(values) => update({ anchor_names: values.length ? values.join(',') : null })}
            className="filter-select"
          />
          <Select
            mode="multiple"
            showSearch
            maxTagCount="responsive"
            aria-label="趋势场控"
            placeholder="场控"
            loading={optionsLoading}
            value={state.control_names}
            options={options?.controls.map((name) => ({ label: name, value: name }))}
            onChange={(values) =>
              update({ control_names: values.length ? values.join(',') : null })
            }
            className="filter-select"
          />
          <Select
            allowClear
            aria-label="ROI目标状态"
            placeholder="ROI目标状态"
            value={state.roi_target_status}
            options={[
              { label: '已达标', value: 'reached' },
              { label: '未达标', value: 'not_reached' },
            ]}
            onChange={(value) => update({ roi_target_status: value ?? null })}
            className="anchor-trend-status-filter"
          />
          <Space size={4} className="anchor-trend-coverage-filter">
            <Typography.Text>完整率≥</Typography.Text>
            <InputNumber
              aria-label="最低完整率"
              min={0}
              max={100}
              precision={0}
              placeholder="不限"
              value={
                state.minimum_coverage_rate === undefined
                  ? null
                  : Math.round(state.minimum_coverage_rate * 100)
              }
              onChange={(value) =>
                update({
                  minimum_coverage_rate: typeof value === 'number' ? String(value / 100) : null,
                })
              }
            />
            <Typography.Text>%</Typography.Text>
          </Space>
          <Select
            allowClear
            aria-label="发送状态"
            placeholder="发送状态"
            value={state.pushed === undefined ? undefined : String(state.pushed)}
            options={[
              { label: '已发送', value: 'true' },
              { label: '未发送', value: 'false' },
            ]}
            onChange={(value) => update({ pushed: value ?? null })}
            className="anchor-trend-status-filter"
          />
          <Button icon={<ReloadOutlined />} onClick={reset}>
            重置筛选
          </Button>
        </Space>
        {optionsError ? (
          <Alert
            type="warning"
            showIcon
            title="筛选选项加载失败，仍可使用 URL 中已有筛选"
            action={<Button onClick={onRetryOptions}>重试选项</Button>}
          />
        ) : null}
      </Space>
    </section>
  )
}

function PeriodSummary({
  current,
  baseline,
}: {
  current: { start: string; end: string } | null
  baseline: { start: string; end: string } | null
}) {
  return (
    <Alert
      type="success"
      showIcon
      title={
        current && baseline
          ? `当前周期 ${current.start} 至 ${current.end}｜基准周期 ${baseline.start} 至 ${baseline.end}`
          : '当前尚无已计算周期，请由运营执行重算。'
      }
      description="两个周期按相同天数比较；完整率和有效小时门槛同时生效。"
    />
  )
}

function TrendSummaryCards({
  summary,
}: {
  summary?: {
    rise_count: number
    fall_count: number
    insufficient_count: number
    reached_count: number
  }
}) {
  const cards = [
    { title: '上涨主播', value: summary?.rise_count ?? 0, className: 'positive' },
    { title: '下跌主播', value: summary?.fall_count ?? 0, className: 'negative' },
    { title: '样本不足', value: summary?.insufficient_count ?? 0, className: 'warning' },
    { title: 'ROI 已达标', value: summary?.reached_count ?? 0, className: 'primary' },
  ]
  return (
    <Row gutter={[12, 12]}>
      {cards.map((card) => (
        <Col xs={12} lg={6} key={card.title}>
          <Card size="small" className={`anchor-trend-stat ${card.className}`}>
            <Statistic title={card.title} value={card.value} />
          </Card>
        </Col>
      ))}
    </Row>
  )
}

function trendStatusTag(item: AnchorTrendItem) {
  const color = item.trend_type === 'rise' ? 'green' : item.trend_type === 'fall' ? 'red' : 'orange'
  return <Tag color={color}>{item.primary_status_name}</Tag>
}

function targetStatus(item: AnchorTrendItem) {
  if (item.roi_target_reached === true) return <Tag color="green">已达标</Tag>
  if (item.roi_target_reached === false) return <Tag color="red">未达标</Tag>
  return <Tag>目标未配置</Tag>
}

function pushStatus(value: string) {
  const labels: Record<
    string,
    { status: 'success' | 'processing' | 'error' | 'default' | 'warning'; text: string }
  > = {
    sent: { status: 'success', text: '已发送' },
    sending: { status: 'processing', text: '发送中' },
    pending: { status: 'warning', text: '待发送' },
    failed: { status: 'error', text: '发送失败' },
    skipped: { status: 'default', text: '已跳过/Mock' },
    unknown: { status: 'default', text: '未知' },
  }
  const item = labels[value] ?? { status: 'default' as const, text: value }
  return <Badge status={item.status} text={item.text} />
}

function signedRate(value: string | number | null): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const percent = Number(value) * 100
  return `${percent > 0 ? '+' : ''}${percent.toFixed(1)}%`
}

function TrendTable({
  rows,
  trendType,
  onOpenDetail,
}: {
  rows: AnchorTrendItem[]
  trendType: AnchorTrendType
  onOpenDetail: (item: AnchorTrendItem) => void
}) {
  const isMobile = useMediaQuery('(max-width: 768px)')

  if (isMobile) {
    return (
      <div className="anchor-trend-mobile-list" data-testid="anchor-trend-mobile-list">
        {rows.map((item) => {
          const majorHours = trendType === 'fall' ? item.major_fall_hours : item.major_rise_hours
          return (
            <Card
              key={item.item_id}
              size="small"
              className={`anchor-trend-mobile-card anchor-trend-mobile-card-${item.trend_type}`}
              role="article"
              aria-labelledby={`anchor-trend-mobile-title-${item.item_id}`}
            >
              <div className="anchor-trend-mobile-header">
                <div className="anchor-trend-mobile-identity">
                  <Space size={6} wrap>
                    <Tag>#{item.rank}</Tag>
                    <Typography.Title id={`anchor-trend-mobile-title-${item.item_id}`} level={5}>
                      {item.anchor_name}
                    </Typography.Title>
                  </Space>
                  <Typography.Text type="secondary">{item.room_name}</Typography.Text>
                </div>
                <Button
                  className="anchor-trend-mobile-detail-button"
                  icon={<EyeOutlined />}
                  aria-label={`查看${item.anchor_name}趋势详情`}
                  onClick={() => onOpenDetail(item)}
                >
                  详情
                </Button>
              </div>

              <div className="anchor-trend-mobile-metrics">
                <div className="anchor-trend-mobile-metric">
                  <Typography.Text type="secondary">当前 / 基准 ROI</Typography.Text>
                  <strong>
                    {formatMetric(item.current_roi, 'ratio')} /{' '}
                    {formatMetric(item.baseline_roi, 'ratio')}
                  </strong>
                </div>
                <div className="anchor-trend-mobile-metric">
                  <Typography.Text type="secondary">ROI 变化</Typography.Text>
                  <Typography.Text type={item.trend_type === 'fall' ? 'danger' : 'success'} strong>
                    {signedRate(item.roi_growth_rate)}
                  </Typography.Text>
                </div>
                <div className="anchor-trend-mobile-metric">
                  <Typography.Text type="secondary">当前 / 基准消耗</Typography.Text>
                  <strong>
                    {formatMetric(item.current_spend, 'currency')} /{' '}
                    {formatMetric(item.baseline_spend, 'currency')}
                  </strong>
                </div>
                <div className="anchor-trend-mobile-metric">
                  <Typography.Text type="secondary">ROI 目标</Typography.Text>
                  <strong>{formatMetric(item.roi_target, 'ratio')}</strong>
                </div>
                <div className="anchor-trend-mobile-metric">
                  <Typography.Text type="secondary">完整率（当前 / 基准）</Typography.Text>
                  <strong>
                    {formatMetric(item.current_coverage_rate, 'percent', 1)} /{' '}
                    {formatMetric(item.baseline_coverage_rate, 'percent', 1)}
                  </strong>
                </div>
                <div className="anchor-trend-mobile-metric">
                  <Typography.Text type="secondary">有效小时（当前 / 基准）</Typography.Text>
                  <strong>
                    {item.current_effective_hours} / {item.baseline_effective_hours}
                  </strong>
                </div>
              </div>

              <Space wrap size={[6, 6]}>
                {trendStatusTag(item)}
                {targetStatus(item)}
                {pushStatus(item.push_status)}
              </Space>
              <Typography.Paragraph className="anchor-trend-mobile-context" type="secondary">
                场控：{item.control_names.length ? item.control_names.join('、') : '—'}
                <br />
                {trendType === 'fall' ? '主要下跌时段' : '主要上涨时段'}：
                {majorHours.length ? majorHours.join('、') : '暂无有效可比小时'}
                <br />
                {item.reasons.join('；') || item.suggestion || '暂无补充说明'}
              </Typography.Paragraph>
            </Card>
          )
        })}
      </div>
    )
  }

  const columns: ColumnsType<AnchorTrendItem> = [
    { title: '排名', dataIndex: 'rank', width: 72, fixed: 'left' },
    {
      title: '主播 / 直播间',
      fixed: 'left',
      width: 190,
      render: (_, item) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{item.anchor_name}</Typography.Text>
          <Typography.Text type="secondary">{item.room_name}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '场控',
      dataIndex: 'control_names',
      width: 150,
      render: (values: string[]) => (values.length ? values.join('、') : '—'),
    },
    {
      title: '当前 / 基准 ROI',
      width: 150,
      render: (_, item) =>
        `${formatMetric(item.current_roi, 'ratio')} / ${formatMetric(item.baseline_roi, 'ratio')}`,
    },
    {
      title: 'ROI变化',
      dataIndex: 'roi_growth_rate',
      width: 105,
      render: (value: AnchorTrendItem['roi_growth_rate'], item) => (
        <Typography.Text type={item.trend_type === 'fall' ? 'danger' : 'success'} strong>
          {signedRate(value)}
        </Typography.Text>
      ),
    },
    {
      title: '当前 / 基准消耗',
      width: 190,
      render: (_, item) =>
        `${formatMetric(item.current_spend, 'currency')} / ${formatMetric(item.baseline_spend, 'currency')}`,
    },
    {
      title: '消耗变化',
      dataIndex: 'spend_growth_rate',
      width: 105,
      render: (value: AnchorTrendItem['spend_growth_rate']) => signedRate(value),
    },
    {
      title: 'ROI目标',
      width: 150,
      render: (_, item) => (
        <Space orientation="vertical" size={2}>
          <span>{formatMetric(item.roi_target, 'ratio')}</span>
          {targetStatus(item)}
        </Space>
      ),
    },
    {
      title: '完整率（当前 / 基准）',
      width: 170,
      render: (_, item) => (
        <div>
          <strong>{formatMetric(item.current_coverage_rate, 'percent', 1)}</strong>
          <br />
          <Typography.Text type="secondary">
            基准 {formatMetric(item.baseline_coverage_rate, 'percent', 1)}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: '有效小时（当前 / 基准）',
      width: 160,
      render: (_, item) => `${item.current_effective_hours} / ${item.baseline_effective_hours}`,
    },
    {
      title: trendType === 'fall' ? '主要下跌时段' : '主要上涨时段',
      width: 170,
      render: (_, item) => {
        const values = trendType === 'fall' ? item.major_fall_hours : item.major_rise_hours
        return values.length ? values.join('、') : '暂无有效可比小时'
      },
    },
    {
      title: '综合判断 / 样本说明',
      width: 260,
      render: (_, item) => (
        <Space orientation="vertical" size={4}>
          {trendStatusTag(item)}
          <Typography.Text type="secondary">
            {item.reasons.join('；') || item.suggestion || '暂无补充说明'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '发送状态 / 目标群',
      width: 180,
      render: (_, item) => (
        <Space orientation="vertical" size={2}>
          {pushStatus(item.push_status)}
          <Typography.Text type="secondary">
            {item.destination_group ?? '默认群/未配置'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 90,
      render: (_, item) => (
        <Button
          size="small"
          icon={<EyeOutlined />}
          aria-label={`查看${item.anchor_name}趋势详情`}
          onClick={() => onOpenDetail(item)}
        >
          详情
        </Button>
      ),
    },
  ]
  return (
    <div data-testid="anchor-trend-desktop-table">
      <Table<AnchorTrendItem>
        rowKey="item_id"
        dataSource={rows}
        columns={columns}
        scroll={{ x: 2300, y: 620 }}
        pagination={{ pageSize: 20, showSizeChanger: true }}
        rowClassName={(item) => `anchor-trend-row anchor-trend-row-${item.trend_type}`}
      />
    </div>
  )
}

function TrendDetailDrawer({
  selection,
  onClose,
}: {
  selection: DetailSelection | null
  onClose: () => void
}) {
  const detail = useQuery({
    queryKey: ['anchor-trend-event', selection?.eventId],
    queryFn: () => getAnchorTrendEvent(selection?.eventId ?? ''),
    enabled: Boolean(selection?.eventId),
  })
  const item = detail.data?.items.find((candidate) => candidate.item_id === selection?.itemId)
  const facts = detail.data?.details.find((candidate) => candidate.item_id === selection?.itemId)

  return (
    <Drawer
      title={selection ? `${selection.anchorName}｜趋势事实详情` : '趋势事实详情'}
      open={Boolean(selection)}
      onClose={onClose}
      destroyOnHidden
      rootClassName="anchor-trend-detail-drawer"
      size={860}
      styles={{ wrapper: { maxWidth: '100vw' } }}
    >
      {detail.isLoading ? (
        <LoadingPanel />
      ) : detail.isError && forbidden(detail.error) ? (
        <Result status="403" title="无权查看该主播趋势详情" />
      ) : detail.isError ? (
        <ErrorPanel onRetry={() => void detail.refetch()} />
      ) : !item || !facts ? (
        <Empty description="趋势详情不存在或已不在当前授权范围内。" />
      ) : (
        <Space orientation="vertical" size={16} className="drawer-stack">
          <Descriptions bordered size="small" column={{ xs: 1, md: 2 }}>
            <Descriptions.Item label="主播">{item.anchor_name}</Descriptions.Item>
            <Descriptions.Item label="直播间">{item.room_name}</Descriptions.Item>
            <Descriptions.Item label="当前周期 ROI">
              {formatMetric(item.current_roi, 'ratio')}
            </Descriptions.Item>
            <Descriptions.Item label="基准周期 ROI">
              {formatMetric(item.baseline_roi, 'ratio')}
            </Descriptions.Item>
            <Descriptions.Item label="当前周期 ROI 分子">
              {formatMetric(facts.roi_numerator.current, 'currency')}
            </Descriptions.Item>
            <Descriptions.Item label="基准周期 ROI 分子">
              {formatMetric(facts.roi_numerator.baseline, 'currency')}
            </Descriptions.Item>
            <Descriptions.Item label="当前周期 ROI 分母">
              {formatMetric(facts.roi_denominator.current, 'currency')}
            </Descriptions.Item>
            <Descriptions.Item label="基准周期 ROI 分母">
              {formatMetric(facts.roi_denominator.baseline, 'currency')}
            </Descriptions.Item>
            <Descriptions.Item label="完整率">
              当前 {formatMetric(item.current_coverage_rate, 'percent', 1)} / 基准{' '}
              {formatMetric(item.baseline_coverage_rate, 'percent', 1)}
            </Descriptions.Item>
            <Descriptions.Item label="主要时段">
              {[...item.major_rise_hours, ...item.major_fall_hours].join('、') || '暂无'}
            </Descriptions.Item>
            <Descriptions.Item label="计算口径" span={2}>
              {item.comparison_basis}
            </Descriptions.Item>
            <Descriptions.Item label="判断说明" span={2}>
              {item.reasons.join('；') || item.suggestion}
            </Descriptions.Item>
          </Descriptions>
          <Tabs
            aria-label="主播趋势事实详情"
            items={[
              {
                key: 'daily',
                label: '逐日汇总',
                children: <DailyDetailTable facts={facts} />,
              },
              {
                key: 'hours',
                label: '24小时明细',
                children: <HourDetailTable facts={facts} />,
              },
              {
                key: 'raw',
                label: '原始事实',
                children: <RawFactsTable rows={facts.raw_records} />,
              },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}

function DailyDetailTable({ facts }: { facts: AnchorTrendItemDetails }) {
  return (
    <Table
      size="small"
      rowKey={(row) => `${row.period}-${row.date}`}
      dataSource={facts.daily}
      pagination={false}
      scroll={{ x: 700 }}
      columns={[
        {
          title: '周期',
          dataIndex: 'period',
          render: (value: string) => (value === 'current' ? '当前周期' : '基准周期'),
        },
        { title: '日期', dataIndex: 'date' },
        {
          title: '成交金额（ROI分子）',
          dataIndex: 'amount',
          align: 'right' as const,
          render: (value: string | number | null) => formatMetric(value, 'currency'),
        },
        {
          title: '消耗（ROI分母）',
          dataIndex: 'spend',
          align: 'right' as const,
          render: (value: string | number | null) => formatMetric(value, 'currency'),
        },
        {
          title: 'ROI',
          dataIndex: 'roi',
          align: 'right' as const,
          render: (value: string | number | null) => formatMetric(value, 'ratio'),
        },
        {
          title: '订单',
          dataIndex: 'orders',
          align: 'right' as const,
          render: (value: string | number | null) => formatMetric(value, 'count', 0),
        },
      ]}
    />
  )
}

function HourDetailTable({ facts }: { facts: AnchorTrendItemDetails }) {
  return (
    <Table
      size="small"
      rowKey="hour"
      dataSource={facts.hours}
      pagination={false}
      scroll={{ x: 1080, y: 520 }}
      columns={[
        { title: '自然小时', dataIndex: 'hour', fixed: 'left' as const, width: 100 },
        {
          title: '当前周期',
          children: [
            {
              title: 'ROI',
              dataIndex: ['current', 'roi'],
              render: (value: string | number | null) => formatMetric(value, 'ratio'),
            },
            {
              title: '成交金额',
              dataIndex: ['current', 'amount'],
              render: (value: string | number | null) => formatMetric(value, 'currency'),
            },
            {
              title: '消耗',
              dataIndex: ['current', 'spend'],
              render: (value: string | number | null) => formatMetric(value, 'currency'),
            },
          ],
        },
        {
          title: '基准周期',
          children: [
            {
              title: 'ROI',
              dataIndex: ['baseline', 'roi'],
              render: (value: string | number | null) => formatMetric(value, 'ratio'),
            },
            {
              title: '成交金额',
              dataIndex: ['baseline', 'amount'],
              render: (value: string | number | null) => formatMetric(value, 'currency'),
            },
            {
              title: '消耗',
              dataIndex: ['baseline', 'spend'],
              render: (value: string | number | null) => formatMetric(value, 'currency'),
            },
          ],
        },
        {
          title: 'ROI差值',
          dataIndex: 'roi_delta',
          render: (value: string | number | null) => formatMetric(value, 'ratio'),
        },
        {
          title: '消耗差值',
          dataIndex: 'spend_difference',
          render: (value: string | number | null) => formatMetric(value, 'currency'),
        },
      ]}
    />
  )
}

function RawFactsTable({ rows }: { rows: AnchorTrendRawRecord[] }) {
  return (
    <Table<AnchorTrendRawRecord>
      size="small"
      rowKey="fact_id"
      dataSource={rows}
      pagination={{ pageSize: 20 }}
      scroll={{ x: 1200, y: 520 }}
      columns={[
        { title: '事实ID', dataIndex: 'fact_id', width: 250, fixed: 'left' },
        {
          title: '周期',
          dataIndex: 'period',
          width: 100,
          render: (value: AnchorTrendRawRecord['period']) =>
            value === 'current' ? '当前' : '基准',
        },
        { title: '日期', dataIndex: 'date', width: 112 },
        { title: '自然小时', dataIndex: 'natural_hour', width: 95 },
        {
          title: '主播',
          dataIndex: 'anchor',
          width: 120,
          render: (value: AnchorTrendRawRecord['anchor']) => value ?? '—',
        },
        {
          title: '场控',
          dataIndex: 'control',
          width: 120,
          render: (value: AnchorTrendRawRecord['control']) => value ?? '—',
        },
        {
          title: '数据状态',
          dataIndex: 'data_status',
          width: 100,
          render: (value: AnchorTrendRawRecord['data_status']) =>
            value === 'complete' ? (
              <Tag color="green">有效</Tag>
            ) : (
              <Tag color="orange">{value}</Tag>
            ),
        },
        {
          title: '原始小时指标事实',
          dataIndex: 'metrics',
          width: 360,
          render: (metrics: AnchorTrendRawRecord['metrics']) => (
            <Typography.Text code>
              {Object.entries(metrics)
                .map(([key, value]) => `${key}=${value ?? '—'}`)
                .join('；')}
            </Typography.Text>
          ),
        },
      ]}
    />
  )
}

function LegacyAlertsPanel({ canOperate }: { canOperate: boolean }) {
  const queryClient = useQueryClient()
  const events = useQuery({ queryKey: ['alert-events'], queryFn: getAlertEvents })
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['alert-events'] })
  const evaluate = useMutation({
    mutationFn: evaluateAlerts,
    onSuccess: (result) => {
      void message.success(
        `评估完成，自动恢复 ${result.recovered} 条，新建 ${result.created} 条，已推送 ${result.sent} 条，失败 ${result.failed} 条`,
      )
      refresh()
    },
  })
  const acknowledge = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => acknowledgeAlert(id, note),
    onSuccess: () => {
      void message.success('预警已确认')
      refresh()
    },
  })
  const retry = useMutation({
    mutationFn: retryAlertPush,
    onSuccess: () => {
      void message.success('推送任务已处理')
      refresh()
    },
  })
  const rows = events.data ?? []

  const columns: ColumnsType<AlertEvent> = [
    {
      title: '等级',
      dataIndex: 'severity',
      width: 86,
      render: (value: AlertEvent['severity']) => (
        <Tag color={severity[value].color}>{severity[value].label}</Tag>
      ),
    },
    { title: '直播间', dataIndex: 'room_name', width: 150 },
    { title: '日期', dataIndex: 'business_date', width: 112 },
    { title: '时段', dataIndex: 'hour_slot', width: 82 },
    {
      title: '主播',
      dataIndex: 'anchor_name',
      width: 110,
      render: (value: AlertEvent['anchor_name']) => value ?? '—',
    },
    {
      title: '场控',
      dataIndex: 'control_name',
      width: 110,
      render: (value: AlertEvent['control_name']) => value ?? '—',
    },
    {
      title: '当前 / 基准',
      width: 140,
      render: (_, row) =>
        `${formatMetric(row.current_value, 'ratio')} / ${formatMetric(row.baseline_value, 'ratio')}`,
    },
    {
      title: 'ROI变化',
      width: 190,
      render: (_, row) => formatRoiChange(row.current_value, row.delta_value, row.growth_percent),
    },
    { title: '判断结果', dataIndex: 'message', width: 320 },
    {
      title: '推送',
      dataIndex: 'push_status',
      width: 120,
      render: (value: AlertEvent['push_status']) => pushStatus(value),
    },
    {
      title: '处理状态',
      width: 120,
      render: (_, row) =>
        row.acknowledged ? (
          <Badge status="success" text="已确认" />
        ) : (
          <Badge status="processing" text="待处理" />
        ),
    },
    ...(canOperate
      ? [
          {
            title: '操作',
            fixed: 'right' as const,
            width: 180,
            render: (_: unknown, row: AlertEvent) => (
              <Space>
                {!row.acknowledged ? (
                  <Popconfirm
                    title="确认处理预警"
                    description="确认已完成人工复核？"
                    onConfirm={() => acknowledge.mutate({ id: row.id, note: '已人工复核' })}
                  >
                    <Button size="small">确认</Button>
                  </Popconfirm>
                ) : null}
                <Button size="small" onClick={() => retry.mutate(row.id)}>
                  重试推送
                </Button>
              </Space>
            ),
          },
        ]
      : []),
  ]

  return (
    <Space orientation="vertical" size={12} className="drawer-stack">
      <Alert
        type="warning"
        showIcon
        title="此页签显式展示历史小时预警，可能包含数据延迟或样本不足等数据质量事件。"
        action={
          canOperate ? (
            <Button loading={evaluate.isPending} onClick={() => evaluate.mutate()}>
              立即评估历史预警
            </Button>
          ) : undefined
        }
      />
      {events.isLoading ? (
        <LoadingPanel />
      ) : events.isError && forbidden(events.error) ? (
        <Result status="403" title="暂无历史预警查看权限" />
      ) : events.isError ? (
        <ErrorPanel onRetry={() => void events.refetch()} />
      ) : !rows.length ? (
        <EmptyPanel />
      ) : (
        <Table<AlertEvent>
          rowKey="id"
          dataSource={rows}
          columns={columns}
          scroll={{ x: 1700, y: 620 }}
          pagination={{ pageSize: 20 }}
        />
      )}
    </Space>
  )
}
