export type AnchorTrendPeriodDays = 1 | 3 | 5 | 7 | 15 | 30
export type AnchorTrendType = 'rise' | 'fall' | 'insufficient'
export type AnchorTrendNotificationType = 'anchor_rise_summary' | 'anchor_fall_summary'
export type AnchorTrendNumeric = string | number | null
export type RoiTargetStatus = 'reached' | 'not_reached'

export interface AnchorTrendPeriod {
  start: string
  end: string
}

export interface AnchorTrendHourValues {
  spend: AnchorTrendNumeric
  amount: AnchorTrendNumeric
  roi: AnchorTrendNumeric
  orders: AnchorTrendNumeric
}

export interface AnchorTrendHourDetail {
  hour: string
  current: AnchorTrendHourValues
  baseline: AnchorTrendHourValues
  roi_delta: AnchorTrendNumeric
  spend_difference: AnchorTrendNumeric
}

export interface AnchorTrendItem {
  item_id: string
  event_id: string
  rank: number
  room_id: string
  room_name: string
  anchor_id: string | null
  anchor_name: string
  control_names: string[]
  trend_type: AnchorTrendType
  current_amount: AnchorTrendNumeric
  baseline_amount: AnchorTrendNumeric
  current_spend: AnchorTrendNumeric
  baseline_spend: AnchorTrendNumeric
  spend_growth_rate: AnchorTrendNumeric
  current_roi: AnchorTrendNumeric
  baseline_roi: AnchorTrendNumeric
  roi_growth_rate: AnchorTrendNumeric
  current_orders: AnchorTrendNumeric
  baseline_orders: AnchorTrendNumeric
  current_order_cost: AnchorTrendNumeric
  baseline_order_cost: AnchorTrendNumeric
  roi_target: AnchorTrendNumeric
  roi_target_gap: AnchorTrendNumeric
  roi_target_reached: boolean | null
  primary_status: string
  primary_status_name: string
  reason_codes: string[]
  reasons: string[]
  major_rise_hours: string[]
  major_fall_hours: string[]
  major_spend_hours: string[]
  hourly_details: AnchorTrendHourDetail[]
  current_effective_days: number
  baseline_effective_days: number
  current_effective_hours: number
  baseline_effective_hours: number
  current_coverage_rate: AnchorTrendNumeric
  baseline_coverage_rate: AnchorTrendNumeric
  comparison_basis: string
  suggestion: string
  push_status: string
  destination_group: string | null
}

export interface AnchorTrendEvent {
  id: string
  rule_id: string
  period_days: AnchorTrendPeriodDays
  current_period_start: string
  current_period_end: string
  baseline_period_start: string
  baseline_period_end: string
  notification_type: AnchorTrendNotificationType | 'anchor_insufficient_summary'
  destination_group: string | null
  room_scope: string[]
  anchor_count: number
  dedup_key: string
  push_status: string
  push_attempts: number
  pushed_at: string | null
  push_error: string | null
  manual_resend: boolean
  source_event_id: string | null
  resend_reason: string | null
  operated_by: string | null
  created_at: string
}

export interface AnchorTrendSummary {
  rise_count: number
  fall_count: number
  insufficient_count: number
  reached_count: number
}

export interface AnchorTrendResponse {
  current_period: AnchorTrendPeriod | null
  baseline_period: AnchorTrendPeriod | null
  rise: AnchorTrendItem[]
  fall: AnchorTrendItem[]
  insufficient: AnchorTrendItem[]
  summary: AnchorTrendSummary
  events: AnchorTrendEvent[]
  event_ids?: Partial<Record<AnchorTrendType, string>>
  data_updated_at?: string | null
}

export interface AnchorTrendDailyDetail {
  period: 'current' | 'baseline'
  date: string
  spend: AnchorTrendNumeric
  amount: AnchorTrendNumeric
  roi: AnchorTrendNumeric
  orders: AnchorTrendNumeric
}

export interface AnchorTrendRawRecord {
  fact_id: string
  period: 'current' | 'baseline'
  date: string
  natural_hour: string
  anchor: string | null
  control: string | null
  data_status: string
  metrics: Record<string, AnchorTrendNumeric>
}

export interface AnchorTrendItemDetails {
  item_id: string
  daily: AnchorTrendDailyDetail[]
  hours: AnchorTrendHourDetail[]
  roi_numerator: { current: AnchorTrendNumeric; baseline: AnchorTrendNumeric }
  roi_denominator: { current: AnchorTrendNumeric; baseline: AnchorTrendNumeric }
  raw_records: AnchorTrendRawRecord[]
}

export interface AnchorTrendEventDetails {
  event: AnchorTrendEvent
  items: AnchorTrendItem[]
  details: AnchorTrendItemDetails[]
}

export interface AnchorTrendFilters {
  period_days: AnchorTrendPeriodDays
  end_date?: string
  room_ids?: string[]
  anchor_ids?: string[]
  anchor_names?: string[]
  control_names?: string[]
  trend_type?: 'all' | AnchorTrendType
  roi_target_status?: RoiTargetStatus
  pushed?: boolean
  destination_group?: string
  minimum_coverage_rate?: number
  limit?: number
}

export interface AnchorTrendRecalculateRequest {
  rule_id?: string
  period_days: AnchorTrendPeriodDays
  end_date?: string
  room_ids: string[]
  anchor_names: string[]
}

export interface AnchorTrendSendRequest {
  rule_id: string
  period: string
  notification_type: AnchorTrendNotificationType
  force_resend?: boolean
  resend_reason?: string
}

export interface AnchorTrendTestRequest {
  notification_type: AnchorTrendNotificationType
  chat_id?: string
}

export interface AnchorTrendPushResult {
  event_id?: string
  push_status: string
  provider?: unknown
  payload?: unknown
}

export interface CurrentUser {
  id: string | null
  name: string
  email?: string | null
  avatar_url?: string | null
  role:
    | 'developer'
    | 'live_manager'
    | 'water_pm'
    | 'primer_pm'
    | 'powder_pm'
    | 'viewer'
    | 'admin'
    | 'operator'
  role_codes?: string[]
  roles?: string[]
  permissions?: string[]
  all_rooms?: boolean
  room_ids?: string[] | null
  room_names?: string[]
  scope_label?: string
  can_export?: boolean
  can_manage_permissions?: boolean
  can_manage_system?: boolean
  can_manage_alerts?: boolean
  can_sync?: boolean
  features?: {
    can_view_dashboard: boolean
    can_export: boolean
    can_view_alerts: boolean
    can_manage_alerts: boolean
    can_manage_permissions: boolean
    can_manage_system: boolean
    can_manage_feishu: boolean
    can_sync: boolean
  }
  auth_mode: string
  csrf_token?: string | null
}
