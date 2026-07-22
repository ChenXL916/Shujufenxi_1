import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

vi.mock('@/api/client', () => ({
  getCurrentUser: vi.fn().mockResolvedValue({
    id: 'admin-1',
    name: '数据管理员',
    email: 'admin@example.com',
    role: 'admin',
    room_ids: [],
  }),
  getFeishuStatus: vi.fn().mockResolvedValue({
    realtime_ready: false,
    user_authorized: false,
  }),
  syncFeishuNow: vi.fn(),
  getFilterOptions: vi.fn().mockResolvedValue({
    min_date: '2026-07-15',
    max_date: '2026-07-15',
    months: ['2026-07'],
    rooms: [],
    anchors: [],
    anchor_members: [],
    controls: [],
    hour_slots: [],
    metrics: [],
    comparison_types: ['previous_day'],
  }),
  getOverview: vi.fn().mockResolvedValue({
    start_date: '2026-07-15',
    end_date: '2026-07-15',
    kpis: [],
    room_ranking: [],
    anchor_match_rate: 1,
    data_completeness: null,
    data_submission_deadline_hour: 8,
    active_alerts: 0,
    sync_mode: 'feishu',
  }),
}))

import App from './App'

test('renders the Chinese dashboard shell and navigation', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/alerts']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  expect(screen.getByText('直播运营驾驶舱')).toBeInTheDocument()
  expect(document.querySelector('.desktop-workspace-title')).toHaveTextContent('运营工作台')
  expect(document.querySelector('.mobile-page-title')).toHaveTextContent('预警中心')
  expect(document.querySelector('.app-shell')).toHaveAttribute('data-theme', 'index-warm-bi')
  expect(document.querySelector('.ant-menu-light')).toBeInTheDocument()
  expect(document.querySelector('.ant-menu-dark')).not.toBeInTheDocument()
  expect(screen.getByText('分析')).toBeInTheDocument()
  expect(screen.getByText('人员')).toBeInTheDocument()
  expect(screen.getByText('监控')).toBeInTheDocument()
  expect(screen.getByText('管理')).toBeInTheDocument()
  expect((await screen.findAllByText('预警中心')).length).toBeGreaterThan(0)
})

test('桌面侧栏折叠时主导航进入图标折叠模式', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/overview']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  const navigation = screen.getByRole('navigation', { name: '主导航' })
  expect(navigation.querySelector('.ant-menu-inline-collapsed')).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '折叠主导航' }))

  await waitFor(() =>
    expect(navigation.querySelector('.ant-menu-inline-collapsed')).toBeInTheDocument(),
  )
})

test('移动主导航使用可聚焦按钮且关闭时不暴露隐藏链接', async () => {
  const mediaQuery = vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query.includes('max-width'),
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/overview']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )

  const trigger = screen.getByRole('button', { name: '打开主导航' })
  trigger.focus()
  expect(trigger).toHaveFocus()
  await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  await waitFor(() =>
    expect(screen.queryByRole('link', { name: '经营总览' })).not.toBeInTheDocument(),
  )

  fireEvent.click(trigger)
  await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'true'))
  expect(await screen.findByRole('link', { name: '经营总览' })).toBeInTheDocument()
  mediaQuery.mockRestore()
})
