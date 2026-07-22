export type NumericValue = string | number | null
export type HourlyAggregationMode = 'sum' | 'daily_average'
export type HourlyChartType = 'line' | 'business_kline' | 'bar'
export type HourlySeriesDimension = 'summary' | 'room' | 'anchor' | 'controller' | 'room_anchor'

export interface HourDescriptor {
  key: string
  label: string
  sort: number
}

export interface DatePeriodPayload {
  start: string
  end: string
  days: number
  complete: boolean
}

export interface BusinessKlinePayload {
  open: NumericValue
  close: NumericValue
  high: NumericValue
  low: NumericValue
  average: NumericValue
  median: NumericValue
  total: NumericValue
  effective_days: number
  first_date: string
  last_date: string
  high_date: string
  low_date: string
}

export interface HourPeriodValues {
  roi: NumericValue
  spend: NumericValue
  metrics: Record<string, NumericValue>
  roi_ohlc: BusinessKlinePayload | null
  spend_ohlc: BusinessKlinePayload | null
  metric_ohlc: Record<string, BusinessKlinePayload | null>
  effective_days: number
  effective_samples: number
  expected_samples: number | null
  coverage_rate: NumericValue
  in_progress: boolean
  future: boolean
}

export interface HourComparisonResult {
  roi_difference: NumericValue
  roi_ratio: NumericValue
  roi_percentage: NumericValue
  roi_growth: NumericValue
  roi_growth_percentage: NumericValue
  spend_difference: NumericValue
  spend_ratio: NumericValue
  spend_percentage: NumericValue
  spend_growth: NumericValue
  spend_growth_percentage: NumericValue
  roi_target_gap: NumericValue
  roi_target_attainment: NumericValue
  roi_target_reached: boolean | null
}

export interface HourStatus {
  code: string
  name: string
  level: 'critical' | 'warning' | 'positive' | 'info' | 'improving' | 'normal' | 'neutral'
  reasons: string[]
  reason_codes: string[]
  should_push: boolean
}

export interface HourlySeriesPoint {
  hour: string
  label: string
  sort: number
  current: HourPeriodValues
  comparison: HourPeriodValues | null
  comparison_result: HourComparisonResult
  roi_target: NumericValue
  target_message: string | null
  status: HourStatus
}

export interface HourlyComparisonSeries {
  series_key: string
  series_name: string
  dimension: HourlySeriesDimension
  room_id: string | null
  room_name: string | null
  product_category: string | null
  anchor_name: string | null
  roi_target: NumericValue
  multiple_targets: boolean
  target_message: string | null
  points: HourlySeriesPoint[]
}

export interface HourlyMetricOption {
  key: string
  name: string
  category: string
  unit: string
  precision: number
  scope: string
  aggregation: string
  numerator: string | null
  denominator: string | null
  direction: string
  default_visible: boolean
  supports_hourly_trend: boolean
  supports_kline: boolean
  supports_alerts: boolean
  is_cumulative: boolean
}

export interface HourlyComparisonResponse {
  meta: {
    timezone: string
    generated_at: string
    data_updated_at: string | null
    period_days: number
    aggregation_mode: HourlyAggregationMode
    chart_type: HourlyChartType
    series_dimension: HourlySeriesDimension
    include_today: boolean
    compare_enabled: boolean
  }
  current_period: DatePeriodPayload
  comparison_period: DatePeriodPayload | null
  hours: HourDescriptor[]
  metrics: HourlyMetricOption[]
  series: HourlyComparisonSeries[]
}

export interface HourlyComparisonRequest {
  endDate?: string
  periodDays?: 1 | 3 | 5 | 7 | 15 | 30
  customStartDate?: string
  customEndDate?: string
  compareEnabled: boolean
  aggregationMode: HourlyAggregationMode
  chartType: HourlyChartType
  metricIds: string[]
  roomIds: string[]
  anchorNames: string[]
  anchorMembers: string[]
  controlNames: string[]
  naturalHours: string[]
  seriesDimension: HourlySeriesDimension
  includeToday: boolean
  includeInProgress: boolean
  showRangeBand: boolean
}

export interface HourlyComparisonDetails {
  summary: HourlySeriesPoint[]
  daily_rows: Array<Record<string, unknown>>
  room_rows: Array<Record<string, unknown>>
  kline_rows: Array<Record<string, unknown>>
  raw_records: Array<Record<string, unknown>>
  page: number
  page_size: number
  raw_total: number
}

export interface RoomMetricTarget {
  id: string
  room_id: string | null
  room_name: string | null
  product_category: string | null
  metric_code: string
  target_value: string | number
  effective_start_date: string | null
  effective_end_date: string | null
  enabled: boolean
  created_at: string
  updated_at: string
  updated_by: string | null
}

export type RoomMetricTargetInput = Omit<
  RoomMetricTarget,
  'id' | 'created_at' | 'updated_at' | 'updated_by'
>

export type HourlyComparisonRuleType = 'hourly_comparison_legacy' | 'anchor_trend_summary'

export interface HourlyComparisonRule {
  id: string
  name: string
  rule_type: HourlyComparisonRuleType
  period_days: 1 | 3 | 5 | 7 | 15 | 30
  spend_increase_threshold: string | number
  spend_decrease_threshold: string | number
  roi_increase_threshold: string | number
  roi_decrease_threshold: string | number
  minimum_spend: string | number
  minimum_orders: number
  minimum_coverage_rate: string | number
  minimum_effective_hours: number
  evaluation_delay_minutes: number
  push_schedule: string
  schedule_timezone: 'Asia/Shanghai'
  applicable_rooms: string[]
  applicable_anchors: string[]
  enabled: boolean
  push_enabled: boolean
  push_chat_id: string | null
  send_rise: boolean
  send_fall: boolean
  rise_limit: number
  fall_limit: number
  send_empty_summary: boolean
  allow_force_resend: boolean
  push_retry_limit: number
  cooldown_minutes: number
  created_at: string
  updated_at: string
  created_by: string | null
  updated_by: string | null
}

export type HourlyComparisonRuleInput = Omit<
  HourlyComparisonRule,
  'id' | 'created_at' | 'updated_at' | 'created_by' | 'updated_by'
>
