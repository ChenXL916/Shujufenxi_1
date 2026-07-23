import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Badge,
  Button,
  Card,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  message,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import {
  getAdminRows,
  getAdminSettings,
  patchAdminRow,
  patchAdminSettings,
  runSourceAction,
} from '@/api/client'
import type { AdminSettingsPatch } from '@/api/client'
import { PageHeader } from '@/components/PageHeader'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import { HourlyComparisonRuleSettings } from '@/features/hourly-comparison/HourlyComparisonRuleSettings'
import { RoomMetricTargetSettings } from '@/features/hourly-comparison/RoomMetricTargetSettings'
import { PermissionManagement } from '@/features/permissions/PermissionManagement'

type Row = Record<string, unknown> & { id?: string }

const tabs = [
  { key: 'sources', label: '数据源' },
  { key: 'metrics', label: '指标字典' },
  { key: 'shifts', label: '班次' },
  { key: 'users', label: '权限' },
  { key: 'settings', label: '系统设置' },
  { key: 'alert-rules', label: '预警规则' },
  { key: 'audit-logs', label: '审计日志' },
]

export function AdminPage({ allowedSections }: { allowedSections?: string[] }) {
  const { section = 'sources' } = useParams()
  const navigate = useNavigate()
  const visibleTabs = allowedSections
    ? tabs.filter((tab) => allowedSections.includes(tab.key))
    : tabs
  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <PageHeader
        title="管理后台"
        description="所有修改均执行服务端角色、CSRF 校验并写入审计日志；密钥永不回显。"
        eyebrow="ADMINISTRATION"
        actions={<Tag color="blue">按角色授权</Tag>}
      />
      <Card className="data-card">
        <Tabs
          activeKey={section}
          items={visibleTabs}
          onChange={(key) => void navigate(`/admin/${key}`)}
        />
        <AdminSection section={section} />
      </Card>
    </Space>
  )
}

function AdminSection({ section }: { section: string }) {
  if (section === 'settings') return <SettingsPanel />
  if (section === 'alert-rules') return <HourlyComparisonRuleSettings />
  if (section === 'users') return <PermissionManagement />
  if (!tabs.some((tab) => tab.key === section)) return <EmptyPanel />
  return <RowsPanel section={section} />
}

function RowsPanel({ section }: { section: string }) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['admin', section], queryFn: () => getAdminRows(section) })
  const action = useMutation({
    mutationFn: ({ id, actionName }: { id: string; actionName: 'test' | 'scan' | 'sync' }) =>
      runSourceAction(id, actionName),
    onSuccess: (result) =>
      message.success(typeof result.message === 'string' ? result.message : '操作完成'),
  })
  const toggle = useMutation({
    mutationFn: ({
      resource,
      id,
      payload,
    }: {
      resource: string
      id: string
      payload: Record<string, unknown>
    }) => patchAdminRow(resource, id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['admin', section] }),
  })
  if (query.isLoading) return <LoadingPanel />
  if (query.isError) return <ErrorPanel onRetry={() => void query.refetch()} />
  const rows = (query.data ?? []) as Row[]
  if (!rows.length) return <EmptyPanel />
  const columns = columnsFor(section, action.mutate, toggle.mutate)
  return (
    <Table<Row>
      rowKey={(row) => row.id ?? JSON.stringify(row)}
      dataSource={rows}
      columns={columns}
      scroll={{ x: 1200, y: 620 }}
      pagination={{ pageSize: 20 }}
    />
  )
}

function columnsFor(
  section: string,
  sourceAction: (value: { id: string; actionName: 'test' | 'scan' | 'sync' }) => void,
  toggle: (value: { resource: string; id: string; payload: Record<string, unknown> }) => void,
) {
  if (section === 'sources') {
    return [
      { title: '名称', dataIndex: 'name', width: 180 },
      { title: '角色', dataIndex: 'source_role', width: 130 },
      { title: 'App Token', dataIndex: 'app_token', width: 170 },
      { title: 'Table ID', dataIndex: 'table_id', width: 160 },
      { title: '默认直播间', dataIndex: 'default_room_name', width: 160 },
      {
        title: '状态',
        dataIndex: 'enabled',
        render: (value: boolean) => (
          <Badge status={value ? 'success' : 'default'} text={value ? '启用' : '停用'} />
        ),
      },
      {
        title: '操作',
        fixed: 'right' as const,
        width: 250,
        render: (_: unknown, row: Row) => (
          <Space>
            {(['test', 'scan', 'sync'] as const).map((name) => (
              <Button
                size="small"
                key={name}
                onClick={() => sourceAction({ id: String(row.id), actionName: name })}
              >
                {name === 'test' ? '测试连接' : name === 'scan' ? '扫描字段' : '立即同步'}
              </Button>
            ))}
          </Space>
        ),
      },
    ]
  }
  if (section === 'metrics') {
    return [
      { title: '字段名', dataIndex: 'source_field_name', width: 200 },
      { title: '显示名', dataIndex: 'display_name', width: 180 },
      { title: '分类', dataIndex: 'category', width: 120 },
      { title: '单位', dataIndex: 'unit', width: 90 },
      { title: '聚合', dataIndex: 'aggregation_strategy', width: 130 },
      { title: '方向', dataIndex: 'direction', width: 100 },
      { title: '图表', dataIndex: 'chartable', render: boolTag },
      { title: '预警', dataIndex: 'alertable', render: boolTag },
      {
        title: '操作',
        render: (_: unknown, row: Row) => (
          <Button
            size="small"
            onClick={() =>
              toggle({
                resource: 'metrics',
                id: String(row.id),
                payload: { alertable: !row.alertable },
              })
            }
          >
            切换预警
          </Button>
        ),
      },
    ]
  }
  if (section === 'shifts') {
    return [
      { title: '班次', dataIndex: 'name' },
      { title: '开始', dataIndex: 'start_time' },
      { title: '结束', dataIndex: 'end_time' },
      { title: '跨天', dataIndex: 'crosses_midnight', render: boolTag },
      { title: '休息', dataIndex: 'is_rest', render: boolTag },
      { title: '启用', dataIndex: 'enabled', render: boolTag },
      {
        title: '操作',
        render: (_: unknown, row: Row) => (
          <Button
            size="small"
            onClick={() =>
              toggle({ resource: 'shifts', id: String(row.id), payload: { enabled: !row.enabled } })
            }
          >
            切换启用
          </Button>
        ),
      },
    ]
  }
  if (section === 'users') {
    return [
      { title: '姓名', dataIndex: 'name' },
      { title: '邮箱', dataIndex: 'email' },
      { title: '角色', dataIndex: 'role_name' },
      {
        title: '授权直播间',
        dataIndex: 'room_ids',
        render: (value: unknown[]) => value?.length ?? 0,
      },
      { title: '启用', dataIndex: 'active', render: boolTag },
    ]
  }
  return [
    { title: '时间', dataIndex: 'created_at', width: 190 },
    { title: '动作', dataIndex: 'action', width: 150 },
    { title: '对象', dataIndex: 'object_type', width: 150 },
    { title: '对象 ID', dataIndex: 'object_id', width: 260 },
    { title: '来源 IP', dataIndex: 'ip_address', width: 140 },
  ]
}

function boolTag(value: boolean) {
  return <Tag color={value ? 'green' : 'default'}>{value ? '是' : '否'}</Tag>
}

function SettingsPanel() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['admin', 'settings'], queryFn: getAdminSettings })
  const save = useMutation({
    mutationFn: patchAdminSettings,
    onSuccess: (settings) => {
      queryClient.setQueryData(['admin', 'settings'], settings)
      message.success('系统设置已安全保存')
    },
    onError: () => message.error('保存失败，请检查输入后重试'),
  })
  if (query.isLoading) return <LoadingPanel />
  if (query.isError) return <ErrorPanel onRetry={() => void query.refetch()} />
  const settings = query.data
  if (!settings) return <EmptyPanel />
  const submit = (values: AdminSettingsPatch) => {
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== undefined && value !== ''),
    ) as AdminSettingsPatch
    save.mutate(payload)
  }
  return (
    <Space orientation="vertical" size={16} className="drawer-stack">
      <Descriptions bordered column={{ xs: 1, md: 2 }}>
        <Descriptions.Item label="飞书应用凭据">
          {boolTag(settings.feishu_app_configured)}
        </Descriptions.Item>
        <Descriptions.Item label="群机器人">
          {boolTag(settings.feishu_bot_configured)}
        </Descriptions.Item>
        <Descriptions.Item label="群机器人 Webhook">
          {boolTag(settings.feishu_bot_webhook_configured)}
        </Descriptions.Item>
        <Descriptions.Item label="应用机器人群 ID">
          {boolTag(settings.feishu_bot_chat_configured)}
        </Descriptions.Item>
      </Descriptions>
      <Alert
        showIcon
        type={
          settings.feishu_app_configured && settings.feishu_bot_configured ? 'success' : 'error'
        }
        title={
          settings.feishu_app_configured && settings.feishu_bot_configured
            ? '飞书数据同步和群推送凭据已配置'
            : '飞书凭据不完整，数据同步或群消息将无法发送'
        }
        description="凭据只会加密保存，页面和接口均不会回显。已配置字段留空即可保持原值。"
      />
      <Form<AdminSettingsPatch>
        className="settings-credentials-form"
        layout="vertical"
        initialValues={{
          live_sync_interval_minutes: settings.live_sync_interval_minutes,
          schedule_sync_interval_minutes: settings.schedule_sync_interval_minutes,
          alert_delay_minutes: settings.alert_delay_minutes,
          daily_summary_time: settings.daily_summary_time,
          feishu_auto_provision_enabled: settings.feishu_auto_provision_enabled,
          feishu_auto_provision_role: settings.feishu_auto_provision_role,
        }}
        onFinish={submit}
      >
        <Typography.Title level={5}>同步与预警</Typography.Title>
        <Space size={16} wrap>
          <Form.Item label="实绩同步间隔（分钟）" name="live_sync_interval_minutes">
            <InputNumber min={1} max={1440} />
          </Form.Item>
          <Form.Item label="排班同步间隔（分钟）" name="schedule_sync_interval_minutes">
            <InputNumber min={1} max={1440} />
          </Form.Item>
          <Form.Item label="预警延迟（分钟）" name="alert_delay_minutes">
            <InputNumber min={1} max={1440} />
          </Form.Item>
        </Space>
        <Typography.Title level={5}>飞书应用凭据</Typography.Title>
        <Form.Item label="App ID" name="feishu_app_id">
          <Input.Password
            autoComplete="new-password"
            placeholder={settings.feishu_app_configured ? '已配置；留空保持不变' : 'cli_xxx'}
          />
        </Form.Item>
        <Form.Item label="App Secret" name="feishu_app_secret">
          <Input.Password
            autoComplete="new-password"
            placeholder={
              settings.feishu_app_configured ? '已配置；留空保持不变' : '请输入 App Secret'
            }
          />
        </Form.Item>
        <Typography.Title level={5}>同事登录与默认权限</Typography.Title>
        <Alert
          showIcon
          type="info"
          title="每位同事使用自己的飞书账号登录"
          description="开启后，飞书应用可用范围内的新用户首次登录会自动建立独立账号；默认角色只负责初始数据范围，之后可在“用户与权限”中按账号改成指定角色或指定直播间。"
        />
        <Form.Item
          label="允许飞书新用户首次登录自动开户"
          name="feishu_auto_provision_enabled"
          valuePropName="checked"
        >
          <Switch aria-label="允许飞书新用户首次登录自动开户" />
        </Form.Item>
        <Form.Item label="新用户默认角色" name="feishu_auto_provision_role">
          <Select options={settings.feishu_auto_provision_role_options} style={{ width: 280 }} />
        </Form.Item>
        <Typography.Title level={5}>群机器人（Webhook 方式推荐）</Typography.Title>
        <Form.Item
          label="群机器人 Webhook"
          name="feishu_bot_webhook_url"
          rules={[
            {
              pattern:
                /^https:\/\/(open\.feishu\.cn|open\.larksuite\.com)\/open-apis\/bot\/v2\/hook\//,
              message: '请输入飞书官方群机器人 Webhook 地址',
            },
          ]}
        >
          <Input.Password
            autoComplete="new-password"
            placeholder={
              settings.feishu_bot_webhook_configured
                ? '已配置；留空保持不变'
                : 'https://open.feishu.cn/open-apis/bot/v2/hook/...'
            }
          />
        </Form.Item>
        <Form.Item label="Webhook 签名密钥（群机器人启用签名校验时填写）" name="feishu_bot_secret">
          <Input.Password
            autoComplete="new-password"
            placeholder={
              settings.feishu_bot_signing_secret_configured ? '已配置；留空保持不变' : '可选'
            }
          />
        </Form.Item>
        <Form.Item label="应用机器人群 ID（App Bot 方式，可选）" name="feishu_bot_chat_id">
          <Input.Password
            autoComplete="new-password"
            placeholder={settings.feishu_bot_chat_configured ? '已配置；留空保持不变' : 'oc_xxx'}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={save.isPending}>
          加密保存飞书设置
        </Button>
      </Form>
      <Divider />
      <RoomMetricTargetSettings />
    </Space>
  )
}
