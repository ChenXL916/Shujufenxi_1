import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse } from 'axios'

const axiosPost = vi.hoisted(() => vi.fn())
const axiosGet = vi.hoisted(() => vi.fn())
const axiosPut = vi.hoisted(() => vi.fn())
const axiosDelete = vi.hoisted(() => vi.fn())
const axiosResponseUse = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: axiosResponseUse },
      },
      post: axiosPost,
      get: axiosGet,
      put: axiosPut,
      delete: axiosDelete,
    })),
  },
}))

import {
  buildAnchorTrendParams,
  deletePermissionUser,
  ensureJsonApiResponse,
  serializeQueryParams,
  syncFeishuNow,
  updatePermissionUserCredentials,
} from './client'

describe('ensureJsonApiResponse', () => {
  const response = (contentType: string, responseType?: 'blob') =>
    ({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': contentType },
      config: { headers: {}, responseType },
    }) as AxiosResponse

  it('accepts JSON API responses', () => {
    const json = response('application/json; charset=utf-8')

    expect(ensureJsonApiResponse(json)).toBe(json)
    expect(axiosResponseUse).toHaveBeenCalledWith(ensureJsonApiResponse)
  })

  it('rejects an HTML SPA fallback instead of passing it to dashboard renderers', () => {
    expect(() => ensureJsonApiResponse(response('text/html; charset=UTF-8'))).toThrow(
      'API 返回了非 JSON 内容',
    )
  })

  it('does not reject download responses', () => {
    const download = response('application/octet-stream', 'blob')

    expect(ensureJsonApiResponse(download)).toBe(download)
  })
})

describe('serializeQueryParams', () => {
  it('uses repeated FastAPI-compatible keys for every multi-select filter', () => {
    const serialized = serializeQueryParams({
      start_date: '2026-07-08',
      room_ids: ['room-a', 'room-b'],
      anchor_names: ['主播甲'],
      control_names: ['场控乙'],
      hour_slots: ['08-09', '09-10'],
      metric_keys: ['period_overall_roi', 'period_spend'],
      ignored: undefined,
    })
    const query = new URLSearchParams(serialized)

    expect(query.get('start_date')).toBe('2026-07-08')
    expect(query.getAll('room_ids')).toEqual(['room-a', 'room-b'])
    expect(query.getAll('anchor_names')).toEqual(['主播甲'])
    expect(query.getAll('control_names')).toEqual(['场控乙'])
    expect(query.getAll('hour_slots')).toEqual(['08-09', '09-10'])
    expect(query.getAll('metric_keys')).toEqual(['period_overall_roi', 'period_spend'])
    expect(serialized).not.toContain('%5B%5D')
  })

  it('serializes every主播趋势筛选为 FastAPI 重复参数', () => {
    const serialized = serializeQueryParams(
      buildAnchorTrendParams({
        period_days: 7,
        end_date: '2026-07-15',
        room_ids: ['room-a', 'room-b'],
        anchor_ids: ['anchor-a'],
        anchor_names: ['主播甲'],
        control_names: ['场控乙'],
        trend_type: 'fall',
        roi_target_status: 'not_reached',
        minimum_coverage_rate: 0.85,
        pushed: false,
        destination_group: '运营群',
      }),
    )
    const query = new URLSearchParams(serialized)

    expect(query.get('period_days')).toBe('7')
    expect(query.getAll('room_ids')).toEqual(['room-a', 'room-b'])
    expect(query.getAll('anchor_ids')).toEqual(['anchor-a'])
    expect(query.getAll('anchor_names')).toEqual(['主播甲'])
    expect(query.getAll('control_names')).toEqual(['场控乙'])
    expect(query.get('trend_type')).toBe('fall')
    expect(query.get('roi_target_status')).toBe('not_reached')
    expect(query.get('minimum_coverage_rate')).toBe('0.85')
    expect(query.get('pushed')).toBe('false')
    expect(query.get('destination_group')).toBe('运营群')
  })

  it('treats zero minimum coverage as no filter so missing-baseline samples remain visible', () => {
    const serialized = serializeQueryParams(
      buildAnchorTrendParams({ period_days: 3, minimum_coverage_rate: 0 }),
    )
    const query = new URLSearchParams(serialized)

    expect(query.has('minimum_coverage_rate')).toBe(false)
  })
})

describe('syncFeishuNow', () => {
  beforeEach(() => {
    axiosPost.mockReset()
    axiosGet.mockReset()
  })

  it('starts a background sync and polls until the real import completes', async () => {
    vi.useFakeTimers()
    axiosPost.mockResolvedValueOnce({
      data: { job_id: 'job-1', status: 'queued' },
    })
    axiosGet
      .mockResolvedValueOnce({ data: { job_id: 'job-1', status: 'running' } })
      .mockResolvedValueOnce({ data: { job_id: 'job-1', status: 'completed' } })

    const result = syncFeishuNow()
    await vi.runAllTimersAsync()

    await expect(result).resolves.toMatchObject({ job_id: 'job-1', status: 'completed' })

    expect(axiosGet).toHaveBeenCalledTimes(2)
    expect(axiosGet).toHaveBeenLastCalledWith('/auth/feishu/sync/job-1', {
      baseURL: '/',
      timeout: 15_000,
    })

    expect(axiosPost).toHaveBeenCalledWith('/auth/feishu/sync', null, {
      baseURL: '/',
      timeout: 15_000,
    })
    vi.useRealTimers()
  })

  it('surfaces the background task error instead of blaming authorization generically', async () => {
    vi.useFakeTimers()
    axiosPost.mockResolvedValueOnce({ data: { job_id: 'job-2', status: 'queued' } })
    axiosGet.mockResolvedValueOnce({
      data: { job_id: 'job-2', status: 'failed', error: '飞书表格读取超时' },
    })

    const result = syncFeishuNow()
    const rejection = expect(result).rejects.toThrow('飞书表格读取超时')
    await vi.runAllTimersAsync()

    await rejection
    vi.useRealTimers()
  })

  it('retries a transient polling disconnect while the background sync continues', async () => {
    vi.useFakeTimers()
    axiosPost.mockResolvedValueOnce({ data: { job_id: 'job-3', status: 'queued' } })
    axiosGet
      .mockRejectedValueOnce(new Error('connection reset'))
      .mockResolvedValueOnce({ data: { job_id: 'job-3', status: 'completed' } })

    const result = syncFeishuNow()
    await vi.runAllTimersAsync()

    await expect(result).resolves.toMatchObject({ job_id: 'job-3', status: 'completed' })
    expect(axiosGet).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })
})

describe('updatePermissionUserCredentials', () => {
  it('updates the selected user login name and optional password through the admin API', async () => {
    axiosPut.mockResolvedValueOnce({ data: { id: 'user-1', username: 'new.login' } })

    await expect(
      updatePermissionUserCredentials('user-1', {
        username: 'new.login',
        password: 'New-password-2026',
      }),
    ).resolves.toMatchObject({ id: 'user-1', username: 'new.login' })

    expect(axiosPut).toHaveBeenCalledWith('/admin/permissions/users/user-1/credentials', {
      username: 'new.login',
      password: 'New-password-2026',
    })
  })
})

describe('deletePermissionUser', () => {
  it('deletes the selected user through the protected admin API', async () => {
    axiosDelete.mockResolvedValueOnce({ status: 204 })

    await expect(deletePermissionUser('user-1')).resolves.toBeUndefined()

    expect(axiosDelete).toHaveBeenCalledWith('/admin/permissions/users/user-1')
  })
})
