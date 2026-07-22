import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import type { KpiPayload } from '@/types/dashboard'
import { KpiCard } from './KpiCard'

const item: KpiPayload = {
  metric_key: 'period_overall_roi',
  name: '时段整体ROI',
  unit: 'ratio',
  precision: 2,
  direction: 'higher_better',
  value: 2,
  comparison: {
    current_value: 2,
    baseline_value: 1,
    delta_value: 1,
    ratio_percent: 200,
    growth_percent: 100,
    direction_status: 'positive',
    explanation: '当前为基准的200%，增长100%',
  },
}

test('KPI卡片支持Enter与Space标准按钮键盘行为', () => {
  const onClick = vi.fn()
  render(<KpiCard item={item} onClick={onClick} />)
  const card = screen.getByRole('button', { name: /时段整体ROI/ })

  card.focus()
  expect(card).toHaveFocus()
  fireEvent.keyDown(card, { key: 'Enter' })
  expect(onClick).toHaveBeenCalledTimes(1)

  const allowedDefault = fireEvent.keyDown(card, { key: ' ', cancelable: true })
  expect(allowedDefault).toBe(false)
  expect(onClick).toHaveBeenCalledTimes(1)
  fireEvent.keyUp(card, { key: ' ' })
  expect(onClick).toHaveBeenCalledTimes(2)

  fireEvent.keyDown(card, { key: 'Enter', repeat: true })
  expect(onClick).toHaveBeenCalledTimes(2)
})

test('KPI趋势与基准组成稳定的元信息排版组', () => {
  const { container } = render(<KpiCard item={item} onClick={vi.fn()} />)
  const meta = container.querySelector('.kpi-meta')

  expect(meta).toBeInTheDocument()
  expect(meta?.querySelector('.kpi-comparison')).toBeInTheDocument()
  expect(meta?.querySelector('.kpi-baseline')).toBeInTheDocument()
})

test('KPI涨跌同时提供图标与明确文字', () => {
  render(<KpiCard item={item} onClick={vi.fn()} />)
  expect(screen.getByText('上涨 100.0%')).toBeInTheDocument()
})

test('消耗单独上涨使用警示中性色而不判定为正向', () => {
  render(<KpiCard item={{ ...item, metric_key: 'period_spend', name: '消耗' }} onClick={vi.fn()} />)
  expect(screen.getByText('上涨 100.0%')).toHaveClass('kpi-trend-label')
  expect(screen.getByText('上涨 100.0%').closest('.kpi-comparison')).toHaveClass('warning')
})

test('KPI合法数值0正常显示且标题和值可读取完整内容', () => {
  render(
    <KpiCard
      item={{
        ...item,
        name: '一个很长但不能丢失的关键指标名称',
        value: 0,
        comparison: { ...item.comparison, current_value: 0 },
      }}
      onClick={vi.fn()}
    />,
  )

  expect(screen.getByText('0.00')).toBeVisible()
  expect(screen.getByText('一个很长但不能丢失的关键指标名称')).toHaveAttribute(
    'title',
    '一个很长但不能丢失的关键指标名称',
  )
  expect(screen.getByText('0.00')).toHaveAttribute('aria-label', expect.stringContaining('0.00'))
})
