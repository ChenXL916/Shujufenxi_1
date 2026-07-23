import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { message } from 'antd'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, vi } from 'vitest'

const { deletePermissionUser, patchAdminSettings, updatePermissionUserCredentials } = vi.hoisted(
  () => ({
    deletePermissionUser: vi.fn().mockResolvedValue(undefined),
    patchAdminSettings: vi.fn().mockResolvedValue({
      live_sync_interval_minutes: 5,
      schedule_sync_interval_minutes: 60,
      alert_delay_minutes: 15,
      daily_summary_time: '09:00',
      feishu_app_configured: true,
      feishu_bot_configured: true,
      feishu_bot_webhook_configured: true,
      feishu_bot_signing_secret_configured: false,
      feishu_bot_chat_configured: false,
      feishu_auto_provision_enabled: true,
      feishu_auto_provision_role: 'live_manager',
      feishu_auto_provision_role_options: [{ value: 'live_manager', label: '直播主管' }],
    }),
    updatePermissionUserCredentials: vi.fn().mockResolvedValue({}),
  }),
)

vi.mock('@/api/client', () => ({
  getAdminSettings: vi.fn().mockResolvedValue({
    live_sync_interval_minutes: 5,
    schedule_sync_interval_minutes: 60,
    alert_delay_minutes: 15,
    daily_summary_time: '09:00',
    feishu_app_configured: false,
    feishu_bot_configured: false,
    feishu_bot_webhook_configured: false,
    feishu_bot_signing_secret_configured: false,
    feishu_bot_chat_configured: false,
    feishu_auto_provision_enabled: true,
    feishu_auto_provision_role: 'live_manager',
    feishu_auto_provision_role_options: [{ value: 'live_manager', label: '直播主管' }],
  }),
  patchAdminSettings,
  getRoomMetricTargets: vi.fn().mockResolvedValue([]),
  getHourlyComparisonRules: vi.fn().mockResolvedValue([]),
  createHourlyComparisonRule: vi.fn(),
  updateHourlyComparisonRule: vi.fn(),
  getAdminRows: vi.fn().mockResolvedValue([]),
  getPermissionOverview: vi.fn().mockResolvedValue({
    current_actor: 'water-user',
    users: [
      {
        id: 'water-user',
        username: 'water_pm_test',
        name: '水散粉PM测试账号',
        email: 'water@example.local',
        role_codes: ['water_pm'],
        status: 'active',
        active: true,
        room_scope_mode: 'role',
        room_ids: ['water-room'],
        room_names: ['Mistine-水散粉'],
        scope_label: 'Mistine-水散粉',
        feishu_bound: false,
        password_login_enabled: true,
        last_login_at: null,
      },
      {
        id: 'feishu-only-user',
        username: null,
        name: '飞书用户待开通网页登录',
        email: 'feishu@example.local',
        role_codes: ['viewer'],
        status: 'active',
        active: true,
        room_scope_mode: 'role',
        room_ids: [],
        room_names: [],
        scope_label: '无直播间',
        feishu_bound: true,
        password_login_enabled: false,
        last_login_at: null,
      },
    ],
    roles: [
      ['developer', '开发者/超级管理员'],
      ['live_manager', '直播主管'],
      ['water_pm', '水散粉PM'],
      ['primer_pm', '妆前乳PM'],
      ['powder_pm', '散粉PM'],
    ].map(([role_code, role_name]) => ({
      id: role_code,
      role_code,
      role_name,
      description: '',
      all_permissions: role_code === 'developer',
      system_role: true,
      active: true,
      permission_codes: role_code === 'developer' ? ['*'] : ['dashboard.view'],
      room_ids: role_code === 'developer' ? [] : ['water-room'],
      room_names: role_code === 'developer' ? [] : ['Mistine-水散粉'],
    })),
    permissions: [{ id: 'p1', code: 'dashboard.view', name: '查看经营数据', description: '' }],
    room_resources: [
      {
        id: 'rr1',
        room_id: 'water-room',
        room_name: 'Mistine-水散粉',
        product_category: 'water_powder',
        permission_group: 'water_pm',
        enabled: true,
      },
    ],
    feishu_groups: [],
  }),
  createPermissionUser: vi.fn(),
  deletePermissionUser,
  resetPermissionUserPassword: vi.fn(),
  updatePermissionUserCredentials,
  updatePermissionUserAccess: vi.fn(),
  updatePermissionRole: vi.fn(),
  updateRoomResource: vi.fn(),
  createFeishuPermissionGroup: vi.fn(),
  updateFeishuPermissionGroup: vi.fn(),
  patchAdminRow: vi.fn(),
  runSourceAction: vi.fn(),
}))

import { AdminPage } from './AdminPage'

afterEach(() => vi.clearAllMocks())

function renderPage(entry = '/admin/settings') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/admin/:section" element={<AdminPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('管理员可在本地安全录入飞书凭据且密钥不回显', async () => {
  vi.spyOn(message, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(message, 'error').mockImplementation(() => undefined as never)
  renderPage()

  expect(await screen.findByText('飞书凭据不完整，数据同步或群消息将无法发送')).toBeInTheDocument()
  const appId = screen.getByLabelText('App ID')
  const appSecret = screen.getByLabelText('App Secret')
  const webhook = screen.getByLabelText('群机器人 Webhook')
  expect(appId).toHaveAttribute('type', 'password')
  expect(appSecret).toHaveAttribute('type', 'password')
  expect(webhook).toHaveAttribute('type', 'password')
  expect(screen.getByRole('button', { name: '加密保存飞书设置' }).closest('form')).toHaveClass(
    'settings-credentials-form',
  )

  fireEvent.change(appId, { target: { value: 'cli_test' } })
  fireEvent.change(appSecret, { target: { value: 'app-secret' } })
  fireEvent.change(webhook, {
    target: { value: 'https://open.feishu.cn/open-apis/bot/v2/hook/test-token' },
  })
  fireEvent.click(screen.getByRole('button', { name: '加密保存飞书设置' }))

  await waitFor(() => expect(patchAdminSettings).toHaveBeenCalledOnce())
  expect(patchAdminSettings.mock.calls[0]?.[0]).toEqual(
    expect.objectContaining({
      feishu_app_id: 'cli_test',
      feishu_app_secret: 'app-secret',
      feishu_bot_webhook_url: 'https://open.feishu.cn/open-apis/bot/v2/hook/test-token',
    }),
  )
})

test('预警规则使用独立且可寻址的管理页签', async () => {
  renderPage('/admin/alert-rules')

  expect(await screen.findByRole('tab', { name: '预警规则' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  expect(screen.getByText('主播趋势与小时比较预警规则')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '新增预警规则' })).toBeInTheDocument()
})

test('用户与权限页展示五角色、权限矩阵、直播间和飞书群范围', async () => {
  renderPage('/admin/users')

  expect(await screen.findByText('水散粉PM测试账号')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '用户管理' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '角色权限矩阵' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '直播间权限' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '飞书群范围' })).toBeInTheDocument()
  expect(screen.getByText('网页账号已启用')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /账号密码/ })).toHaveLength(2)

  const currentUserRow = screen.getByText('水散粉PM测试账号').closest('tr')
  expect(currentUserRow).not.toBeNull()
  expect(within(currentUserRow as HTMLElement).getByRole('button', { name: /删除/ })).toBeDisabled()

  const feishuOnlyRow = screen.getByText('飞书用户待开通网页登录').closest('tr')
  expect(feishuOnlyRow).not.toBeNull()
  const credentialsButton = within(feishuOnlyRow as HTMLElement).getByRole('button', {
    name: /账号密码/,
  })
  expect(credentialsButton).toBeEnabled()
  fireEvent.click(credentialsButton)
  fireEvent.change(await screen.findByLabelText('网页登录名'), {
    target: { value: 'feishu.viewer' },
  })
  fireEvent.change(screen.getByLabelText('新密码（可选）'), {
    target: { value: 'Feishu-viewer-password-2026' },
  })
  fireEvent.change(screen.getByLabelText('确认新密码'), {
    target: { value: 'Feishu-viewer-password-2026' },
  })
  fireEvent.click(screen.getByRole('button', { name: '保存账号设置' }))
  await waitFor(() =>
    expect(updatePermissionUserCredentials).toHaveBeenCalledWith('feishu-only-user', {
      username: 'feishu.viewer',
      password: 'Feishu-viewer-password-2026',
    }),
  )
  await waitFor(() => expect(screen.queryByLabelText('网页登录名')).not.toBeInTheDocument())

  const refreshedFeishuRow = screen.getByText('飞书用户待开通网页登录').closest('tr')
  expect(refreshedFeishuRow).not.toBeNull()
  fireEvent.click(within(refreshedFeishuRow as HTMLElement).getByRole('button', { name: /删除/ }))
  expect(await screen.findByText('确认删除用户“飞书用户待开通网页登录”？')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '确认删除' }))
  await waitFor(() => expect(deletePermissionUser.mock.calls[0]?.[0]).toBe('feishu-only-user'))

  fireEvent.click(screen.getByRole('button', { name: /新增用户/ }))
  expect(await screen.findByLabelText('初始密码')).toHaveAttribute('type', 'password')
  fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }))

  fireEvent.click(screen.getByRole('tab', { name: '角色权限矩阵' }))
  expect(await screen.findByText('开发者/超级管理员')).toBeInTheDocument()
  expect(screen.getByText('直播主管')).toBeInTheDocument()
  expect(screen.getAllByText('水散粉PM').length).toBeGreaterThan(0)
  expect(screen.getByText('妆前乳PM')).toBeInTheDocument()
  expect(screen.getByText('散粉PM')).toBeInTheDocument()
})
