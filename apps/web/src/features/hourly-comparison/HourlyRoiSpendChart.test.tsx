import type { EChartsType } from 'echarts/core'
import { describe, expect, test, vi } from 'vitest'
import { clearHourlySeriesFocus, focusHourlySeries } from './hourlyChartInteraction'

describe('24小时曲线悬停联动', () => {
  test('悬停突出同名业务系列，离开后恢复全部系列', () => {
    const dispatchAction = vi.fn()
    const chart = { dispatchAction } as unknown as EChartsType

    focusHourlySeries(chart, '全部直播间 当前ROI')
    expect(dispatchAction).toHaveBeenNthCalledWith(1, { type: 'downplay' })
    expect(dispatchAction).toHaveBeenNthCalledWith(2, {
      type: 'highlight',
      seriesName: '全部直播间 当前ROI',
    })

    clearHourlySeriesFocus(chart)
    expect(dispatchAction).toHaveBeenLastCalledWith({ type: 'downplay' })
  })

  test('没有系列名称时不触发图表状态变更', () => {
    const dispatchAction = vi.fn()
    const chart = { dispatchAction } as unknown as EChartsType
    focusHourlySeries(chart, undefined)
    expect(dispatchAction).not.toHaveBeenCalled()
  })
})
