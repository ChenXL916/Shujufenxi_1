import { describe, expect, it, vi } from 'vitest'

const axiosPost = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: { request: { use: vi.fn() } },
      post: axiosPost,
    })),
  },
}))

import { buildAnchorTrendParams, serializeQueryParams, syncFeishuNow } from './client'

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
  it('allows enough time for the real multi-source Feishu import to finish', async () => {
    axiosPost.mockResolvedValueOnce({ data: { status: 'completed' } })

    await expect(syncFeishuNow()).resolves.toEqual({ status: 'completed' })

    expect(axiosPost).toHaveBeenCalledWith('/auth/feishu/sync', null, {
      baseURL: '/',
      timeout: 120_000,
    })
  })
})
