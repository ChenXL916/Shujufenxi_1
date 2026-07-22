import {
  AlertOutlined,
  AuditOutlined,
  BarChartOutlined,
  BellOutlined,
  BookOutlined,
  CalendarOutlined,
  CloudSyncOutlined,
  ControlOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DoubleLeftOutlined,
  DoubleRightOutlined,
  LineChartOutlined,
  MenuOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  SlidersOutlined,
  SwapOutlined,
  TeamOutlined,
  TableOutlined,
} from '@ant-design/icons'
import { Alert, Avatar, Button, Drawer, Layout, Menu, Result, Tooltip, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { lazy, Suspense, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AccessibilityEnhancer } from '@/components/AccessibilityEnhancer'
import { LoadingPanel } from '@/components/StatePanel'
import { StatusBadge } from '@/components/StatusBadge'
import { restoreFocusAfterOverlayClose } from '@/utils/focus'
import { getCurrentUser, getFeishuStatus, syncFeishuNow } from '@/api/client'

const OverviewPage = lazy(() =>
  import('@/pages/OverviewPage').then((module) => ({ default: module.OverviewPage })),
)
const TimelinePage = lazy(() =>
  import('@/pages/TimelinePage').then((module) => ({ default: module.TimelinePage })),
)
const ComparisonPage = lazy(() =>
  import('@/pages/ComparisonPage').then((module) => ({ default: module.ComparisonPage })),
)
const AnalysisPage = lazy(() =>
  import('@/pages/AnalysisPage').then((module) => ({ default: module.AnalysisPage })),
)
const PivotPage = lazy(() =>
  import('@/pages/PivotPage').then((module) => ({ default: module.PivotPage })),
)
const AlertsPage = lazy(() =>
  import('@/pages/AlertsPage').then((module) => ({ default: module.AlertsPage })),
)
const AdminPage = lazy(() =>
  import('@/pages/AdminPage').then((module) => ({ default: module.AdminPage })),
)

const { Header, Content, Sider } = Layout
const items: MenuProps['items'] = [
  {
    key: 'analysis',
    type: 'group',
    label: '分析',
    children: [
      {
        key: '/overview',
        icon: <DashboardOutlined />,
        label: <Link to="/overview">经营总览</Link>,
      },
      {
        key: '/timeline',
        icon: <LineChartOutlined />,
        label: <Link to="/timeline">小时趋势</Link>,
      },
      {
        key: '/comparison',
        icon: <SwapOutlined />,
        label: <Link to="/comparison">数据对比</Link>,
      },
    ],
  },
  {
    key: 'people',
    type: 'group',
    label: '人员',
    children: [
      { key: '/anchors', icon: <TeamOutlined />, label: <Link to="/anchors">主播分析</Link> },
      {
        key: '/controls',
        icon: <ControlOutlined />,
        label: <Link to="/controls">场控分析</Link>,
      },
      {
        key: '/pairings',
        icon: <TeamOutlined />,
        label: <Link to="/pairings">主播场控搭配</Link>,
      },
      {
        key: '/pivot',
        icon: <TableOutlined />,
        label: <Link to="/pivot">主播场控透视</Link>,
      },
    ],
  },
  {
    key: 'monitoring',
    type: 'group',
    label: '监控',
    children: [
      { key: '/alerts', icon: <AlertOutlined />, label: <Link to="/alerts">预警中心</Link> },
    ],
  },
  {
    key: 'administration',
    type: 'group',
    label: '管理',
    children: [
      {
        key: '/admin/sources',
        icon: <DatabaseOutlined />,
        label: <Link to="/admin/sources">数据源管理</Link>,
      },
      {
        key: '/admin/metrics',
        icon: <BookOutlined />,
        label: <Link to="/admin/metrics">指标字典</Link>,
      },
      {
        key: '/admin/shifts',
        icon: <CalendarOutlined />,
        label: <Link to="/admin/shifts">班次配置</Link>,
      },
      {
        key: '/admin/alert-rules',
        icon: <SlidersOutlined />,
        label: <Link to="/admin/alert-rules">预警与 ROI 目标</Link>,
      },
      {
        key: '/admin/users',
        icon: <SafetyCertificateOutlined />,
        label: <Link to="/admin/users">用户与权限</Link>,
      },
      {
        key: '/admin/audit-logs',
        icon: <AuditOutlined />,
        label: <Link to="/admin/audit-logs">审计日志</Link>,
      },
      {
        key: '/admin/settings',
        icon: <SettingOutlined />,
        label: <Link to="/admin/settings">系统设置</Link>,
      },
    ],
  },
]

const pageTitles: Record<string, string> = {
  '/overview': '经营总览',
  '/timeline': '小时趋势',
  '/comparison': '数据对比',
  '/anchors': '主播分析',
  '/controls': '场控分析',
  '/pairings': '主播场控搭配',
  '/pivot': '主播场控透视',
  '/alerts': '预警中心',
  '/admin/sources': '数据源管理',
  '/admin/metrics': '指标字典',
  '/admin/shifts': '班次配置',
  '/admin/users': '用户与权限',
  '/admin/alert-rules': '预警与 ROI 目标',
  '/admin/audit-logs': '审计日志',
  '/admin/settings': '系统设置',
}

function formatUpdatedAt(value?: string | null): string {
  if (!value) return '尚无成功同步'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

const roleLabels: Record<string, string> = {
  developer: '开发者/超级管理员',
  live_manager: '直播主管',
  water_pm: '水散粉PM',
  primer_pm: '妆前乳PM',
  powder_pm: '散粉PM',
  viewer: '受限查看者',
  admin: '管理员（兼容）',
  operator: '运营（兼容）',
}

export default function App() {
  const location = useLocation()
  const queryClient = useQueryClient()
  const [mobileNavigation, setMobileNavigation] = useState(false)
  const mobileNavigationTriggerRef = useRef<HTMLButtonElement | null>(null)
  const [mobile, setMobile] = useState(false)
  const [navigationCollapsed, setNavigationCollapsed] = useState(false)
  const closeMobileNavigation = () => {
    const trigger = mobileNavigationTriggerRef.current
    setMobileNavigation(false)
    restoreFocusAfterOverlayClose(trigger)
  }
  const currentUser = useQuery({
    queryKey: ['current-user'],
    queryFn: getCurrentUser,
    staleTime: 60_000,
  })
  const feishu = useQuery({
    queryKey: ['feishu-status'],
    queryFn: getFeishuStatus,
    refetchInterval: 60_000,
    enabled: currentUser.isSuccess,
  })
  const sync = useMutation({
    mutationFn: syncFeishuNow,
    onSuccess: async () => {
      message.success('飞书真实数据已同步')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['feishu-status'] }),
        queryClient.invalidateQueries({ queryKey: ['overview'] }),
        queryClient.invalidateQueries({ queryKey: ['filter-options'] }),
      ])
    },
    onError: () => message.error('同步失败，请检查飞书授权状态'),
  })
  const realtimeReady = feishu.data?.realtime_ready === true
  const permissionCodes = currentUser.data?.permissions ?? []
  const hasAllPermissions = permissionCodes.includes('*')
  const canViewDashboard =
    hasAllPermissions ||
    permissionCodes.includes('dashboard.view') ||
    currentUser.data?.features?.can_view_dashboard === true
  const canViewAlerts =
    hasAllPermissions ||
    permissionCodes.includes('alert.view') ||
    currentUser.data?.features?.can_view_alerts === true
  const canManagePermissions =
    hasAllPermissions ||
    permissionCodes.includes('permission.manage') ||
    currentUser.data?.features?.can_manage_permissions === true
  const pageTitle = pageTitles[location.pathname] ?? '直播数据驾驶舱'
  const userName = currentUser.data?.name || '当前用户'
  const userRole = currentUser.data?.role
    ? (roleLabels[currentUser.data.role] ?? currentUser.data.role)
    : currentUser.isError
      ? '权限信息不可用'
      : '加载中'
  const scopeLabel = currentUser.data?.scope_label ?? '数据范围加载中'
  const canSync =
    currentUser.data?.features?.can_sync ??
    ['developer', 'admin', 'operator'].includes(currentUser.data?.role ?? '')
  const noRoomAccess =
    currentUser.data?.room_ids !== null && currentUser.data?.room_ids?.length === 0
  const handleSync = () => {
    if (!feishu.data?.user_authorized) {
      window.location.assign('/auth/feishu/login')
      return
    }
    sync.mutate()
  }
  const statusTone = feishu.data?.last_error
    ? 'negative'
    : realtimeReady
      ? 'positive'
      : feishu.isLoading
        ? 'info'
        : 'warning'
  const statusLabel = feishu.data?.last_error
    ? '同步失败'
    : realtimeReady
      ? '数据正常'
      : feishu.isLoading
        ? '正在检查'
        : feishu.data?.user_authorized
          ? '部分延迟'
          : '等待授权'
  if (currentUser.isLoading) {
    return (
      <Layout className="app-shell" data-theme="index-warm-bi">
        <LoadingPanel />
      </Layout>
    )
  }
  if (currentUser.isError || !currentUser.data) {
    return (
      <Layout className="app-shell" data-theme="index-warm-bi">
        <Result
          status="403"
          title="请先使用飞书登录"
          subTitle="每位同事都需要使用自己的飞书账号登录，系统会按账号分别应用角色和直播间权限。"
          extra={
            <Button type="primary" onClick={() => window.location.assign('/auth/feishu/login')}>
              使用飞书登录
            </Button>
          }
        />
      </Layout>
    )
  }
  const visibleItems = items?.filter((item) => {
    if (!item || !('key' in item)) return false
    if (item.key === 'analysis' || item.key === 'people') return canViewDashboard
    if (item.key === 'monitoring') return canViewAlerts
    if (item.key === 'administration') return canManagePermissions
    return false
  })
  const defaultRoute = canViewDashboard ? '/overview' : canViewAlerts ? '/alerts' : '/access-denied'
  const accessDenied = (
    <Result
      status="403"
      title="当前账号没有此功能权限"
      subTitle="请联系管理员在“用户与权限”中调整角色或直播间范围。"
    />
  )
  const navigation = (
    <Menu
      theme="light"
      mode="inline"
      inlineCollapsed={!mobile && navigationCollapsed}
      className={!mobile && navigationCollapsed ? 'desktop-navigation-collapsed' : undefined}
      selectedKeys={[location.pathname]}
      items={visibleItems}
      onClick={() => mobile && setMobileNavigation(false)}
    />
  )
  return (
    <Layout className="app-shell" data-theme="index-warm-bi">
      <AccessibilityEnhancer />
      <Sider
        width={236}
        breakpoint="lg"
        collapsed={mobile || navigationCollapsed}
        collapsedWidth={mobile ? 0 : 80}
        trigger={null}
        className="app-sider"
        onBreakpoint={(broken) => {
          setMobile(broken)
          if (!broken) setMobileNavigation(false)
        }}
      >
        {!mobile ? (
          <div className={`sider-inner${navigationCollapsed ? ' is-collapsed' : ''}`}>
            <div className="brand">
              <span className="brand-mark">
                <BarChartOutlined />
              </span>
              <span className="brand-copy" aria-hidden={navigationCollapsed}>
                <strong>直播运营驾驶舱</strong>
                <small>LIVE OPS</small>
              </span>
              <Button
                type="text"
                className="sider-collapse-button"
                icon={navigationCollapsed ? <DoubleRightOutlined /> : <DoubleLeftOutlined />}
                aria-label={navigationCollapsed ? '展开主导航' : '折叠主导航'}
                onClick={() => setNavigationCollapsed((value) => !value)}
              />
            </div>
            <nav className="sider-navigation" aria-label="主导航">
              {navigation}
            </nav>
            <div className="sider-user">
              <Avatar className="user-avatar">{userName.slice(0, 1)}</Avatar>
              <div className="sider-user-copy" aria-hidden={navigationCollapsed}>
                <strong title={userName}>{userName}</strong>
                <span title={userRole}>{userRole}</span>
              </div>
              {canManagePermissions ? (
                <Tooltip title="系统设置">
                  <Link
                    className="sider-user-settings"
                    to="/admin/settings"
                    aria-label="打开系统设置"
                    aria-hidden={navigationCollapsed}
                    tabIndex={navigationCollapsed ? -1 : undefined}
                  >
                    <SettingOutlined />
                  </Link>
                </Tooltip>
              ) : null}
            </div>
          </div>
        ) : null}
      </Sider>
      <Layout className="app-main-layout">
        <Header className="app-header">
          <div className="header-context">
            <Button
              ref={mobileNavigationTriggerRef}
              className="mobile-nav-trigger"
              type="text"
              icon={<MenuOutlined />}
              aria-label="打开主导航"
              aria-controls="mobile-main-navigation"
              aria-expanded={mobileNavigation}
              onClick={() => setMobileNavigation(true)}
            />
            <div className="header-title-stack">
              <Typography.Title level={4} className="desktop-workspace-title">
                运营工作台
              </Typography.Title>
              <Typography.Title level={4} className="mobile-page-title">
                {pageTitle}
              </Typography.Title>
              <Typography.Text
                type="secondary"
                className="header-subtitle"
                title={`直播运营驾驶舱 · Asia/Shanghai · ${scopeLabel}`}
              >
                直播运营驾驶舱 · Asia/Shanghai · {scopeLabel}
              </Typography.Text>
            </div>
          </div>
          <div className="header-tools">
            <div className="sync-meta">
              <StatusBadge tone={statusTone} title={feishu.data?.last_error ?? undefined}>
                {statusLabel}
              </StatusBadge>
              <span className="sync-updated-at">
                更新 {formatUpdatedAt(feishu.data?.last_success_at)}
              </span>
            </div>
            {canSync ? (
              <Button
                className="header-sync-button"
                icon={<CloudSyncOutlined />}
                loading={sync.isPending}
                onClick={handleSync}
              >
                {feishu.data?.user_authorized ? '立即同步' : '授权飞书'}
              </Button>
            ) : null}
            {canViewAlerts ? (
              <Tooltip title="预警中心">
                <Link to="/alerts" className="header-icon-link" aria-label="打开预警中心">
                  <BellOutlined />
                </Link>
              </Tooltip>
            ) : null}
            <Tooltip title={`${userName} · ${userRole}`}>
              <Avatar className="user-avatar">{userName.slice(0, 1)}</Avatar>
            </Tooltip>
          </div>
        </Header>
        <Content className="app-content">
          {noRoomAccess ? (
            <Alert
              showIcon
              type="warning"
              title="当前账号尚未分配直播间"
              description="登录已经成功，但数据范围为空。请联系管理员在“用户与权限”中分配角色或直播间。"
              style={{ marginBottom: 16 }}
            />
          ) : null}
          <Suspense fallback={<LoadingPanel />}>
            <Routes>
              <Route path="/" element={<Navigate to={defaultRoute} replace />} />
              <Route
                path="/overview"
                element={canViewDashboard ? <OverviewPage /> : accessDenied}
              />
              <Route
                path="/timeline"
                element={canViewDashboard ? <TimelinePage /> : accessDenied}
              />
              <Route
                path="/comparison"
                element={canViewDashboard ? <ComparisonPage /> : accessDenied}
              />
              <Route
                path="/anchors"
                element={canViewDashboard ? <AnalysisPage dimension="anchors" /> : accessDenied}
              />
              <Route
                path="/controls"
                element={canViewDashboard ? <AnalysisPage dimension="controls" /> : accessDenied}
              />
              <Route
                path="/pairings"
                element={canViewDashboard ? <AnalysisPage dimension="pairings" /> : accessDenied}
              />
              <Route path="/pivot" element={canViewDashboard ? <PivotPage /> : accessDenied} />
              <Route path="/alerts" element={canViewAlerts ? <AlertsPage /> : accessDenied} />
              <Route
                path="/admin/:section"
                element={canManagePermissions ? <AdminPage /> : accessDenied}
              />
              <Route path="/access-denied" element={accessDenied} />
              <Route path="*" element={<Navigate to={defaultRoute} replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
      <Drawer
        id="mobile-main-navigation"
        title="直播运营驾驶舱"
        placement="left"
        size={286}
        open={mobile && mobileNavigation}
        destroyOnHidden
        rootClassName="mobile-navigation-drawer"
        onClose={closeMobileNavigation}
      >
        <nav aria-label="移动主导航">{navigation}</nav>
        {canSync ? (
          <Button
            block
            className="mobile-drawer-sync"
            icon={<CloudSyncOutlined />}
            loading={sync.isPending}
            onClick={() => {
              setMobileNavigation(false)
              handleSync()
            }}
          >
            {feishu.data?.user_authorized ? '立即同步' : '授权飞书'}
          </Button>
        ) : null}
        <div className="sider-user mobile-sider-user">
          <Avatar className="user-avatar">{userName.slice(0, 1)}</Avatar>
          <div className="sider-user-copy">
            <strong>{userName}</strong>
            <span>{userRole}</span>
          </div>
        </div>
      </Drawer>
    </Layout>
  )
}
