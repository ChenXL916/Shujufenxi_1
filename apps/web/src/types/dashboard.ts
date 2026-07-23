export type Grain = 'hour' | 'point'
export type DateMode = 'day' | 'month'

export interface RoomOption {
  id: string
  name: string
}
export interface MetricOption {
  key: string
  name: string
  category: string
  unit: string
  precision: number
  scope: string
  aggregation: string
  numerator: string | null
  denominator: string | null
  direction: 'higher_better' | 'lower_better' | 'neutral' | 'contextual'
  default_visible: boolean
  supports_hourly_trend: boolean
  supports_kline: boolean
  supports_alerts: boolean
  is_cumulative: boolean
}
export interface FilterOptions {
  min_date: string | null
  max_date: string | null
  months: string[]
  rooms: RoomOption[]
  anchors: string[]
  anchor_members: string[]
  controls: string[]
  hour_slots: string[]
  metrics: MetricOption[]
  comparison_types: string[]
}
export interface ComparisonPayload {
  current_value: string | number | null
  baseline_value: string | number | null
  delta_value: string | number | null
  ratio_percent: string | number | null
  growth_percent: string | number | null
  direction_status: string
  explanation: string
}
export interface KpiPayload {
  metric_key: string
  name: string
  unit: string
  precision: number
  direction: MetricOption['direction']
  value: string | number | null
  comparison: ComparisonPayload
}
export interface OverviewResponse {
  start_date: string | null
  end_date: string | null
  kpis: KpiPayload[]
  room_ranking: Array<{
    room_id: string
    room_name: string
    amount: number | string
    roi: number | string
    hours: number
  }>
  anchor_match_rate: string | number | null
  data_completeness: string | number | null
  data_submission_deadline_hour: number
  active_alerts: number
  sync_mode: 'feishu' | 'feishu_base_export' | 'fixture_mock'
}
export interface XItem {
  key: string
  fact_id: string | null
  point_id: string | null
  label: string
  date: string
  hour_slot: string | null
  anchor: string | null
  control: string | null
  observed_at: string | null
}
export interface TimelineSeries {
  metric_key: string
  name: string
  unit: string
  axis_group: string
  data: Array<number | string | null>
  source_items?: Array<XItem | null>
}
export interface TimelineGroup {
  group_key: string
  group_label: string
  x_items: XItem[]
  series: TimelineSeries[]
  annotations: Array<Record<string, unknown>>
}
export interface TimelineResponse {
  grain: Grain
  groups: TimelineGroup[]
}
export interface DetailResponse {
  id: string
  room: string
  base: Record<string, unknown>
  metrics: Record<string, string | number | null>
  raw_payload: Record<string, unknown> | null
  points: Array<Record<string, unknown>>
}
export interface DashboardFilters {
  startDate?: string
  endDate?: string
  dateMode: DateMode
  roomIds: string[]
  anchors: string[]
  anchorMembers: string[]
  controls: string[]
  hours: string[]
  metricKeys: string[]
  grain: Grain
}
export interface AnalysisRow {
  [metricKey: string]: string | number | null
  key: string
  name: string
  valid_hours: number
  room_count: number
  period_overall_amount: string | number | null
  period_spend: string | number | null
  period_overall_roi: string | number | null
  period_net_roi: string | number | null
  period_order_count: string | number | null
  period_overall_order_cost: string | number | null
  period_viewers: string | number | null
  period_buyers: string | number | null
}
export interface AnchorHourDetailRow {
  key: string
  fact_id: string
  business_date: string
  hour_slot: string
  hour_order: number
  room_id: string
  room_name: string
  anchor_name: string
  control_name: string | null
  latest_observed_at: string | null
  anchor_match_status: string
  data_status: string
  metrics: Record<string, string | number | null>
}
export interface AnchorHourDetailResponse {
  items: AnchorHourDetailRow[]
  total: number
  page: number
  page_size: number
  metric_keys: string[]
}
export interface ComparisonRow extends ComparisonPayload {
  metric_key: string
  name: string
  unit: string
}
export interface PivotNode {
  key: string
  level: 'anchor' | 'control' | 'date' | 'hour'
  label: string
  valid_hours: number
  period_overall_amount: string | number | null
  period_spend: string | number | null
  period_overall_roi: string | number | null
  period_order_count: string | number | null
  period_overall_order_cost: string | number | null
  period_viewers: string | number | null
  children?: PivotNode[]
}

export interface AlertEvent {
  id: string
  triggered_at: string
  room_id: string
  room_name: string
  business_date: string
  hour_slot: string
  anchor_name: string | null
  control_name: string | null
  metric_key: string | null
  current_value: string | number | null
  baseline_value: string | number | null
  delta_value: string | number | null
  ratio_percent: string | number | null
  growth_percent: string | number | null
  severity: 'info' | 'warning' | 'critical'
  title: string
  message: string
  suggestion: string
  push_status: string
  push_attempts: number
  acknowledged: boolean
  resolution_note: string | null
}
