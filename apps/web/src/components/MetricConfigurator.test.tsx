import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { MetricConfigurator } from './MetricConfigurator'

const metrics = [
  { key: 'roi', name: '时段整体支付ROI', category: 'ROI', scope: 'derived' },
  { key: 'spend', name: '时段消耗', category: '消耗', scope: 'period' },
  { key: 'amount', name: '时段成交金额', category: '金额', scope: 'period' },
  { key: 'orders', name: '时段成交单数', category: '订单', scope: 'period' },
  { key: 'viewers', name: '时段观看人数', category: '人数', scope: 'period' },
]

test('支持固定指标、选择上限和恢复默认配置', async () => {
  const onChange = vi.fn()
  render(
    <MetricConfigurator
      metrics={metrics}
      value={['roi', 'spend']}
      defaultMetricKeys={['roi', 'spend']}
      lockedMetricKeys={['roi', 'spend']}
      maxSelected={4}
      onChange={onChange}
    />,
  )

  fireEvent.click(screen.getByRole('button', { name: '配置指标，已选 2 个' }))
  const roi = await screen.findByRole('checkbox', { name: /时段整体支付ROI/ })
  expect(roi).toBeChecked()
  expect(roi).toBeDisabled()

  fireEvent.click(screen.getByRole('checkbox', { name: /时段成交金额/ }))
  fireEvent.click(screen.getByRole('checkbox', { name: /时段成交单数/ }))
  expect(screen.getByRole('checkbox', { name: /时段观看人数/ })).toBeDisabled()

  fireEvent.click(screen.getByRole('button', { name: /恢复默认配置/ }))
  expect(screen.getByRole('checkbox', { name: /时段成交金额/ })).not.toBeChecked()
  expect(screen.getByRole('checkbox', { name: /时段观看人数/ })).not.toBeDisabled()

  fireEvent.click(screen.getByRole('checkbox', { name: /时段观看人数/ }))
  fireEvent.click(screen.getByRole('button', { name: '应用 3 个指标' }))
  expect(onChange).toHaveBeenCalledWith(['roi', 'spend', 'viewers'])
})
