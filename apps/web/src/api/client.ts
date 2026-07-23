import axios, { type AxiosResponse } from 'axios'
import type {
  AnchorTrendEventDetails,
  AnchorTrendFilters,
  AnchorTrendPushResult,
  AnchorTrendRecalculateRequest,
  AnchorTrendResponse,
  AnchorTrendSendRequest,
  AnchorTrendTestRequest,
  CurrentUser,
} from '@/types/anchorTrends'
import type {
  AnalysisRow,
  AlertEvent,
  AnchorHourDetailResponse,
  ComparisonRow,
  DashboardFilters,
  DetailResponse,
  FilterOptions,
  OverviewResponse,
  PivotNode,
  TimelineResponse,
} from '@/types/dashboard'
import type {
  HourlyComparisonDetails,
  HourlyComparisonRequest,
  HourlyComparisonResponse,
  HourlyComparisonRule,
  HourlyComparisonRuleInput,
  RoomMetricTarget,
  RoomMetricTargetInput,
} from '@/types/hourlyComparison'
import type {
  FeishuPermissionGroup,
  FeishuPermissionGroupInput,
  PermissionOverview,
  PermissionRole,
  PermissionRoleInput,
  PermissionUser,
  PermissionUserCredentialsInput,
  PermissionUserInput,
  RoomResource,
  RoomResourceInput,
} from '@/types/permissions'

export interface FeishuStatus {
  credentials_configured: boolean
  live_source_configured: boolean
  user_authorized: boolean
  refresh_valid: boolean
  scope: string[]
  last_success_at: string | null
  last_error: string | null
  realtime_ready: boolean
  login_url: string
  sync_interval_minutes: number
}

export interface ManualFeishuSyncJob {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'skipped'
  requested_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
  result: Record<string, unknown> | null
  accepted?: boolean
}

export interface AdminSettings {
  live_sync_interval_minutes: number
  schedule_sync_interval_minutes: number
  alert_delay_minutes: number
  daily_summary_time: string
  feishu_app_configured: boolean
  feishu_bot_configured: boolean
  feishu_bot_webhook_configured: boolean
  feishu_bot_signing_secret_configured: boolean
  feishu_bot_chat_configured: boolean
  feishu_auto_provision_enabled: boolean
  feishu_auto_provision_role: string
  feishu_auto_provision_role_options: Array<{ value: string; label: string }>
}

export interface AdminSettingsPatch {
  live_sync_interval_minutes?: number
  schedule_sync_interval_minutes?: number
  alert_delay_minutes?: number
  daily_summary_time?: string
  feishu_app_id?: string
  feishu_app_secret?: string
  feishu_bot_webhook_url?: string
  feishu_bot_secret?: string
  feishu_bot_chat_id?: string
  feishu_auto_provision_enabled?: boolean
  feishu_auto_provision_role?: string
}

export function serializeQueryParams(parameters: Record<string, unknown>): string {
  const search = new URLSearchParams()
  const append = (key: string, value: unknown) => {
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      search.append(key, String(value))
    }
  }
  Object.entries(parameters).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return
    if (Array.isArray(value)) {
      value.forEach((item) => append(key, item))
      return
    }
    append(key, value)
  })
  return search.toString()
}

export function buildAnchorTrendParams(filters: AnchorTrendFilters): Record<string, unknown> {
  return {
    period_days: filters.period_days,
    end_date: filters.end_date,
    room_ids: filters.room_ids,
    anchor_ids: filters.anchor_ids,
    anchor_names: filters.anchor_names,
    control_names: filters.control_names,
    trend_type: filters.trend_type,
    roi_target_status: filters.roi_target_status,
    pushed: filters.pushed,
    destination_group: filters.destination_group,
    minimum_coverage_rate:
      filters.minimum_coverage_rate !== undefined && filters.minimum_coverage_rate > 0
        ? filters.minimum_coverage_rate
        : undefined,
    limit: filters.limit,
  }
}

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
  paramsSerializer: { serialize: serializeQueryParams },
})
client.interceptors.request.use((config) => {
  const csrf = document.cookie
    .split('; ')
    .find((item) => item.startsWith('live_ops_csrf='))
    ?.split('=')[1]
  if (csrf && config.method?.toLowerCase() !== 'get') {
    config.headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  return config
})

export class UnexpectedApiResponseError extends Error {
  constructor() {
    super('API 返回了非 JSON 内容，请检查生产后端与反向代理配置。')
    this.name = 'UnexpectedApiResponseError'
  }
}

export function ensureJsonApiResponse<T>(response: AxiosResponse<T>): AxiosResponse<T> {
  if (response.config.responseType === 'blob' || response.status === 204) return response

  const contentType = String(response.headers?.['content-type'] ?? '').toLowerCase()
  if (!contentType.includes('json')) throw new UnexpectedApiResponseError()
  return response
}

client.interceptors.response.use(ensureJsonApiResponse)

function params(filters: DashboardFilters) {
  return {
    start_date: filters.startDate,
    end_date: filters.endDate,
    room_ids: filters.roomIds,
    anchor_names: filters.anchors,
    anchor_members: filters.anchorMembers,
    control_names: filters.controls,
    hour_slots: filters.hours,
  }
}

function hourlyParams(filters: HourlyComparisonRequest) {
  return {
    end_date: filters.endDate,
    period_days: filters.periodDays,
    custom_start_date: filters.customStartDate,
    custom_end_date: filters.customEndDate,
    compare_enabled: filters.compareEnabled,
    aggregation_mode: filters.aggregationMode,
    chart_type: filters.chartType,
    metric_ids: filters.metricIds,
    room_ids: filters.roomIds,
    anchor_names: filters.anchorNames,
    anchor_member_ids: filters.anchorMembers,
    controller_ids: filters.controlNames,
    natural_hours: filters.naturalHours,
    series_dimension: filters.seriesDimension,
    include_today: filters.includeToday,
    include_in_progress: filters.includeInProgress,
    show_range_band: filters.showRangeBand,
  }
}

export async function getFilterOptions(): Promise<FilterOptions> {
  return (await client.get<FilterOptions>('/filters/options')).data
}
export async function getOverview(filters: DashboardFilters): Promise<OverviewResponse> {
  return (await client.get<OverviewResponse>('/dashboard/overview', { params: params(filters) }))
    .data
}

export async function getHourlyComparison(
  filters: HourlyComparisonRequest,
): Promise<HourlyComparisonResponse> {
  return (
    await client.get<HourlyComparisonResponse>('/overview/hourly-comparison', {
      params: hourlyParams(filters),
    })
  ).data
}

export async function getHourlyComparisonDetails(
  filters: HourlyComparisonRequest,
  naturalHour: string,
  page = 1,
): Promise<HourlyComparisonDetails> {
  return (
    await client.get<HourlyComparisonDetails>('/overview/hourly-comparison/details', {
      params: { ...hourlyParams(filters), natural_hour: naturalHour, page, page_size: 50 },
    })
  ).data
}

export async function downloadHourlyComparison(filters: HourlyComparisonRequest): Promise<void> {
  const response = await client.post<Blob>('/overview/hourly-comparison/export', null, {
    params: hourlyParams(filters),
    responseType: 'blob',
  })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const matchedName = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = matchedName ?? '24小时ROI消耗对比.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function getRoomMetricTargets(): Promise<RoomMetricTarget[]> {
  return (await client.get<RoomMetricTarget[]>('/settings/room-metric-targets')).data
}

export async function createRoomMetricTarget(
  payload: RoomMetricTargetInput,
): Promise<RoomMetricTarget> {
  return (await client.post<RoomMetricTarget>('/settings/room-metric-targets', payload)).data
}

export async function updateRoomMetricTarget(
  id: string,
  payload: RoomMetricTargetInput,
): Promise<RoomMetricTarget> {
  return (await client.put<RoomMetricTarget>(`/settings/room-metric-targets/${id}`, payload)).data
}

export async function getHourlyComparisonRules(): Promise<HourlyComparisonRule[]> {
  return (await client.get<HourlyComparisonRule[]>('/settings/hourly-comparison-rules')).data
}

export async function createHourlyComparisonRule(
  payload: HourlyComparisonRuleInput,
): Promise<HourlyComparisonRule> {
  return (await client.post<HourlyComparisonRule>('/settings/hourly-comparison-rules', payload))
    .data
}

export async function updateHourlyComparisonRule(
  id: string,
  payload: HourlyComparisonRuleInput,
): Promise<HourlyComparisonRule> {
  return (
    await client.put<HourlyComparisonRule>(`/settings/hourly-comparison-rules/${id}`, payload)
  ).data
}

export async function getTimeline(filters: DashboardFilters): Promise<TimelineResponse> {
  return (
    await client.get<TimelineResponse>('/charts/timeline', {
      params: { ...params(filters), grain: filters.grain, metric_keys: filters.metricKeys },
    })
  ).data
}
export async function getDetail(id: string, grain: 'hour' | 'point'): Promise<DetailResponse> {
  const path = grain === 'hour' ? `/hourly-facts/${id}` : `/live-points/${id}`
  return (await client.get<DetailResponse>(path)).data
}
export async function getAnalysis(
  dimension: 'anchors' | 'controls' | 'pairings',
  filters: DashboardFilters,
): Promise<AnalysisRow[]> {
  const path = dimension === 'pairings' ? '/analytics/pairings' : `/analytics/${dimension}/summary`
  return (
    await client.get<AnalysisRow[]>(path, {
      params: { ...params(filters), metric_keys: filters.metricKeys },
    })
  ).data
}
export async function getAnchorHourDetails(
  filters: DashboardFilters,
  page = 1,
  pageSize = 50,
): Promise<AnchorHourDetailResponse> {
  return (
    await client.get<AnchorHourDetailResponse>('/analytics/anchors/hours', {
      params: {
        ...params(filters),
        metric_keys: filters.metricKeys,
        page,
        page_size: pageSize,
      },
    })
  ).data
}
export async function getComparisons(
  filters: DashboardFilters,
  comparisonType: string,
): Promise<ComparisonRow[]> {
  return (
    await client.get<ComparisonRow[]>('/comparisons', {
      params: {
        ...params(filters),
        comparison_type: comparisonType,
        metric_keys: filters.metricKeys,
      },
    })
  ).data
}
export async function getPivot(filters: DashboardFilters): Promise<PivotNode[]> {
  return (await client.get<PivotNode[]>('/pivot/anchor-control', { params: params(filters) })).data
}
export async function downloadExport(filters: DashboardFilters, fileFormat: 'csv' | 'xlsx') {
  const response = await client.post<Blob>('/exports', null, {
    params: { ...params(filters), file_format: fileFormat },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `live-ops-pivot.${fileFormat}`
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function getAnchorTrends(filters: AnchorTrendFilters): Promise<AnchorTrendResponse> {
  return (
    await client.get<AnchorTrendResponse>('/alerts/anchor-trends', {
      params: buildAnchorTrendParams(filters),
    })
  ).data
}

export async function recalculateAnchorTrends(
  payload: AnchorTrendRecalculateRequest,
): Promise<AnchorTrendResponse> {
  return (await client.post<AnchorTrendResponse>('/alerts/anchor-trends/recalculate', payload)).data
}

export async function getAnchorTrendEvent(eventId: string): Promise<AnchorTrendEventDetails> {
  return (await client.get<AnchorTrendEventDetails>(`/alerts/anchor-trends/${eventId}`)).data
}

export async function sendAnchorTrendSummary(
  payload: AnchorTrendSendRequest,
): Promise<AnchorTrendPushResult> {
  return (await client.post<AnchorTrendPushResult>('/alerts/anchor-trends/send', payload)).data
}

export async function testAnchorTrendPush(
  payload: AnchorTrendTestRequest,
): Promise<AnchorTrendPushResult> {
  return (await client.post<AnchorTrendPushResult>('/alerts/anchor-trends/test-push', payload)).data
}

export async function getAlertEvents(): Promise<AlertEvent[]> {
  return (await client.get<AlertEvent[]>('/alerts/events')).data
}
export async function evaluateAlerts(): Promise<{
  recovered: number
  created: number
  queued: number
  sent: number
  failed: number
  skipped: number
}> {
  return (
    await client.post<{
      recovered: number
      created: number
      queued: number
      sent: number
      failed: number
      skipped: number
    }>('/alerts/evaluate')
  ).data
}
export async function acknowledgeAlert(id: string, resolutionNote: string) {
  return (
    await client.post<{ id: string; acknowledged: boolean }>(`/alerts/events/${id}/acknowledge`, {
      resolution_note: resolutionNote,
    })
  ).data
}
export async function retryAlertPush(id: string) {
  return (
    await client.post<{ mocked: boolean; payload?: unknown }>(`/alerts/events/${id}/retry-push`)
  ).data
}
export async function testAlertPush() {
  return (await client.post<{ mocked: boolean; payload: unknown }>('/alerts/test-push')).data
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return (await client.get<CurrentUser>('/auth/me', { baseURL: '/' })).data
}

export async function loginWithPassword(payload: {
  username: string
  password: string
}): Promise<{ authenticated: boolean; redirect_url: string }> {
  return (
    await client.post<{ authenticated: boolean; redirect_url: string }>(
      '/auth/password/login',
      payload,
      { baseURL: '/' },
    )
  ).data
}

export async function logoutCurrentUser(): Promise<void> {
  await client.post('/auth/logout', null, { baseURL: '/' })
}

export async function getFeishuStatus(): Promise<FeishuStatus> {
  return (await client.get<FeishuStatus>('/auth/feishu/status', { baseURL: '/' })).data
}

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

export async function syncFeishuNow(): Promise<ManualFeishuSyncJob> {
  const accepted = (
    await client.post<ManualFeishuSyncJob>('/auth/feishu/sync', null, {
      baseURL: '/',
      timeout: 15_000,
    })
  ).data
  if (accepted.status === 'completed') return accepted
  if (!accepted.job_id) throw new Error('同步任务未返回任务编号，请重试')

  let consecutivePollFailures = 0
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await wait(2_000)
    let job: ManualFeishuSyncJob
    try {
      job = (
        await client.get<ManualFeishuSyncJob>(`/auth/feishu/sync/${accepted.job_id}`, {
          baseURL: '/',
          timeout: 15_000,
        })
      ).data
      consecutivePollFailures = 0
    } catch {
      consecutivePollFailures += 1
      if (consecutivePollFailures < 5) continue
      throw new Error('同步仍在后台运行，但状态查询暂时中断，请稍后刷新页面')
    }
    if (job.status === 'completed') return job
    if (job.status === 'failed' || job.status === 'skipped') {
      throw new Error(job.error || '同步未完成，请稍后重试')
    }
  }
  throw new Error('同步仍在后台运行，请稍后刷新页面查看最新数据')
}

export async function getAdminRows(path: string): Promise<Array<Record<string, unknown>>> {
  return (await client.get<Array<Record<string, unknown>>>(`/admin/${path}`)).data
}
export async function getAdminSettings(): Promise<AdminSettings> {
  return (await client.get<AdminSettings>('/admin/settings')).data
}
export async function patchAdminSettings(payload: AdminSettingsPatch): Promise<AdminSettings> {
  return (await client.patch<AdminSettings>('/admin/settings', payload)).data
}
export async function runSourceAction(sourceId: string, action: 'test' | 'scan' | 'sync') {
  const method = action === 'scan' ? 'get' : 'post'
  return (
    await client.request<Record<string, unknown>>({
      method,
      url: `/admin/sources/${sourceId}/${action}`,
    })
  ).data
}
export async function patchAdminRow(
  resource: string,
  id: string,
  payload: Record<string, unknown>,
) {
  return (await client.patch<Record<string, unknown>>(`/admin/${resource}/${id}`, payload)).data
}

export async function getPermissionOverview(): Promise<PermissionOverview> {
  return (await client.get<PermissionOverview>('/admin/permissions/overview')).data
}

export async function createPermissionUser(
  payload: PermissionUserInput & {
    username: string
    name: string
    email?: string
    password: string
  },
): Promise<PermissionUser> {
  return (await client.post<PermissionUser>('/admin/permissions/users', payload)).data
}

export async function resetPermissionUserPassword(
  userId: string,
  password: string,
): Promise<PermissionUser> {
  return (
    await client.put<PermissionUser>(`/admin/permissions/users/${userId}/password`, { password })
  ).data
}

export async function updatePermissionUserCredentials(
  userId: string,
  payload: PermissionUserCredentialsInput,
): Promise<PermissionUser> {
  return (
    await client.put<PermissionUser>(`/admin/permissions/users/${userId}/credentials`, payload)
  ).data
}

export async function deletePermissionUser(userId: string): Promise<void> {
  await client.delete(`/admin/permissions/users/${userId}`)
}

export async function updatePermissionUserAccess(
  userId: string,
  payload: PermissionUserInput,
): Promise<PermissionUser> {
  return (await client.put<PermissionUser>(`/admin/permissions/users/${userId}/access`, payload))
    .data
}

export async function updatePermissionRole(
  roleId: string,
  payload: PermissionRoleInput,
): Promise<PermissionRole> {
  return (await client.put<PermissionRole>(`/admin/permissions/roles/${roleId}`, payload)).data
}

export async function updateRoomResource(
  resourceId: string,
  payload: RoomResourceInput,
): Promise<RoomResource> {
  return (
    await client.put<RoomResource>(`/admin/permissions/room-resources/${resourceId}`, payload)
  ).data
}

export async function createFeishuPermissionGroup(
  payload: FeishuPermissionGroupInput & { chat_id: string },
): Promise<FeishuPermissionGroup> {
  return (await client.post<FeishuPermissionGroup>('/admin/permissions/feishu-groups', payload))
    .data
}

export async function updateFeishuPermissionGroup(
  groupId: string,
  payload: Omit<FeishuPermissionGroupInput, 'chat_id'>,
): Promise<FeishuPermissionGroup> {
  return (
    await client.put<FeishuPermissionGroup>(`/admin/permissions/feishu-groups/${groupId}`, payload)
  ).data
}
