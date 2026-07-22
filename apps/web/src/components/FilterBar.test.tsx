import { fireEvent, render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { FilterBar } from './FilterBar'
import type { DashboardFilters } from '@/types/dashboard'

test('switching to month mode selects the full calendar month', () => {
  const update = vi.fn()
  const filters: DashboardFilters = {
    startDate: '2026-07-08',
    endDate: '2026-07-08',
    dateMode: 'day',
    roomIds: [],
    anchors: [],
    anchorMembers: [],
    controls: [],
    hours: [],
    metricKeys: [],
    grain: 'hour',
  }

  render(<FilterBar filters={filters} update={update} reset={vi.fn()} />)
  fireEvent.click(screen.getByText('按月'))

  expect(update).toHaveBeenCalledWith({
    dateMode: 'month',
    startDate: '2026-07-01',
    endDate: '2026-07-31',
  })
})

test('经营总览快捷周期按结束日更新全局三日范围', () => {
  const update = vi.fn()
  const filters: DashboardFilters = {
    startDate: '2026-07-15',
    endDate: '2026-07-15',
    dateMode: 'day',
    roomIds: [],
    anchors: [],
    anchorMembers: [],
    controls: [],
    hours: [],
    metricKeys: [],
    grain: 'hour',
  }

  render(<FilterBar filters={filters} update={update} reset={vi.fn()} showPeriodPresets />)
  fireEvent.click(screen.getByRole('radio', { name: '3天' }))

  expect(update).toHaveBeenCalledWith({
    dateMode: 'day',
    startDate: '2026-07-13',
    endDate: '2026-07-15',
  })
})

test('经营总览筛选按时间与业务范围分组并显示已选摘要', () => {
  const update = vi.fn()
  const filters: DashboardFilters = {
    startDate: '2026-07-15',
    endDate: '2026-07-15',
    dateMode: 'day',
    roomIds: ['room-1'],
    anchors: [],
    anchorMembers: [],
    controls: [],
    hours: [],
    metricKeys: [],
    grain: 'hour',
  }

  render(<FilterBar filters={filters} update={update} reset={vi.fn()} showPeriodPresets />)

  expect(screen.getByText('时间范围')).toBeInTheDocument()
  expect(screen.getByText('业务范围')).toBeInTheDocument()
  expect(screen.getByText('已选 2 项')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '清空全部筛选' })).toBeInTheDocument()
})

test('shows the anchor member filter supplied by the API', () => {
  const filters: DashboardFilters = {
    dateMode: 'day',
    roomIds: [],
    anchors: [],
    anchorMembers: [],
    controls: [],
    hours: [],
    metricKeys: [],
    grain: 'hour',
  }

  render(
    <FilterBar
      filters={filters}
      update={vi.fn()}
      reset={vi.fn()}
      options={{
        min_date: '2026-07-01',
        max_date: '2026-07-14',
        months: ['2026-07'],
        rooms: [],
        anchors: [],
        anchor_members: ['李昕'],
        controls: [],
        hour_slots: [],
        metrics: [],
        comparison_types: ['previous_day'],
      }}
    />,
  )

  expect(screen.getByLabelText('主播成员')).toBeInTheDocument()
})

test('移动筛选使用全屏Drawer且提供固定语义的重置和应用操作', async () => {
  const mediaQuery = vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query.includes('max-width: 768px'),
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )
  const filters: DashboardFilters = {
    dateMode: 'day',
    roomIds: ['room-1'],
    anchors: [],
    anchorMembers: [],
    controls: [],
    hours: [],
    metricKeys: [],
    grain: 'hour',
  }

  render(<FilterBar filters={filters} update={vi.fn()} reset={vi.fn()} />)
  const toggle = screen.getByRole('button', { name: '打开更多筛选，已选 1 项' })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')

  fireEvent.click(toggle)

  expect(await screen.findByRole('dialog', { name: '更多筛选' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '应用筛选' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重置全部筛选' })).toBeInTheDocument()
  mediaQuery.mockRestore()
})
