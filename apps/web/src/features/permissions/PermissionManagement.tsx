import {
  DeleteOutlined,
  EditOutlined,
  KeyOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import axios from 'axios'
import { useState } from 'react'
import {
  createFeishuPermissionGroup,
  createPermissionUser,
  deletePermissionUser,
  getPermissionOverview,
  updateFeishuPermissionGroup,
  updatePermissionRole,
  updatePermissionUserAccess,
  updatePermissionUserCredentials,
  updateRoomResource,
} from '@/api/client'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '@/components/StatePanel'
import type {
  FeishuPermissionGroup,
  PermissionOverview,
  PermissionRole,
  PermissionUser,
  RoomResource,
} from '@/types/permissions'

type UserFormValues = {
  username: string
  name: string
  email: string
  password: string
  role_codes: string[]
  room_scope_mode: 'role' | 'custom'
  room_ids: string[]
  active: boolean
}

type CredentialsFormValues = {
  username: string
  password?: string
  password_confirmation?: string
}

type RoleFormValues = {
  role_name: string
  description: string
  permission_codes: string[]
  room_ids: string[]
  active: boolean
}

type ResourceFormValues = {
  product_category: string
  permission_group: string
  enabled: boolean
}

type GroupFormValues = {
  name: string
  chat_id: string
  room_ids: string[]
  enabled: boolean
}

const roleColor: Record<string, string> = {
  developer: 'purple',
  live_manager: 'blue',
  water_pm: 'cyan',
  primer_pm: 'geekblue',
  powder_pm: 'magenta',
  viewer: 'default',
}

function permissionErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<unknown>(error)) {
    const data = error.response?.data
    if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
      return data.detail
    }
  }
  return fallback
}

export function PermissionManagement() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['admin', 'permissions', 'overview'],
    queryFn: getPermissionOverview,
  })
  const [userEditor, setUserEditor] = useState<PermissionUser | 'new' | null>(null)
  const [credentialsEditor, setCredentialsEditor] = useState<PermissionUser | null>(null)
  const [roleEditor, setRoleEditor] = useState<PermissionRole | null>(null)
  const [resourceEditor, setResourceEditor] = useState<RoomResource | null>(null)
  const [groupEditor, setGroupEditor] = useState<FeishuPermissionGroup | 'new' | null>(null)

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin', 'permissions'] })
  }
  const saveUser = useMutation({
    mutationFn: async (values: UserFormValues) => {
      const roomIds = values.room_scope_mode === 'role' ? null : values.room_ids
      if (userEditor === 'new') {
        return createPermissionUser({
          username: values.username,
          name: values.name,
          email: values.email.trim() || undefined,
          password: values.password,
          role_codes: values.role_codes,
          room_ids: roomIds,
          active: values.active,
        })
      }
      if (!userEditor) throw new Error('未选择用户')
      return updatePermissionUserAccess(userEditor.id, {
        role_codes: values.role_codes,
        room_ids: roomIds,
        active: values.active,
      })
    },
    onSuccess: async () => {
      setUserEditor(null)
      await refresh()
      message.success('用户角色和数据范围已保存，权限立即按服务端配置生效')
    },
    onError: () => message.error('用户权限保存失败，请检查角色和直播间配置'),
  })
  const saveCredentials = useMutation({
    mutationFn: async (values: CredentialsFormValues) => {
      if (!credentialsEditor) throw new Error('未选择用户')
      return updatePermissionUserCredentials(credentialsEditor.id, {
        username: values.username.trim(),
        password: values.password || undefined,
      })
    },
    onSuccess: async (_, values) => {
      setCredentialsEditor(null)
      await refresh()
      message.success(
        values.password
          ? '网页登录名和新密码已保存，旧密码立即失效'
          : '网页登录名已保存，原密码保持不变',
      )
    },
    onError: (error) =>
      message.error(permissionErrorMessage(error, '账号密码保存失败，请检查输入后重试')),
  })
  const removeUser = useMutation({
    mutationFn: deletePermissionUser,
    onSuccess: async () => {
      await refresh()
      message.success('用户已删除，原账号、飞书绑定、角色和个人数据范围已立即失效')
    },
    onError: (error) => message.error(permissionErrorMessage(error, '用户删除失败，请稍后重试')),
  })
  const saveRole = useMutation({
    mutationFn: async (values: RoleFormValues) => {
      if (!roleEditor) throw new Error('未选择角色')
      return updatePermissionRole(roleEditor.id, values)
    },
    onSuccess: async () => {
      setRoleEditor(null)
      await refresh()
      message.success('角色权限矩阵已保存')
    },
    onError: () => message.error('角色权限保存失败'),
  })
  const saveResource = useMutation({
    mutationFn: async (values: ResourceFormValues) => {
      if (!resourceEditor) throw new Error('未选择直播间')
      return updateRoomResource(resourceEditor.id, values)
    },
    onSuccess: async () => {
      setResourceEditor(null)
      await refresh()
      message.success('直播间产品分类和权限组已保存')
    },
    onError: () => message.error('直播间权限配置保存失败'),
  })
  const saveGroup = useMutation({
    mutationFn: async (values: GroupFormValues) => {
      if (groupEditor === 'new') return createFeishuPermissionGroup(values)
      if (!groupEditor) throw new Error('未选择飞书群')
      return updateFeishuPermissionGroup(groupEditor.id, {
        name: values.name,
        room_ids: values.room_ids,
        enabled: values.enabled,
      })
    },
    onSuccess: async () => {
      setGroupEditor(null)
      await refresh()
      message.success('飞书群直播间范围已保存')
    },
    onError: () => message.error('飞书群范围保存失败'),
  })

  if (query.isLoading) return <LoadingPanel />
  if (query.isError) return <ErrorPanel onRetry={() => void query.refetch()} />
  if (!query.data) return <EmptyPanel />
  const data = query.data

  const items = [
    {
      key: 'users',
      label: '用户管理',
      children: (
        <UsersPanel
          data={data}
          deletingUserId={removeUser.isPending ? removeUser.variables : undefined}
          onDelete={(userId) => removeUser.mutate(userId)}
          onEdit={setUserEditor}
          onEditCredentials={setCredentialsEditor}
        />
      ),
    },
    {
      key: 'roles',
      label: '角色权限矩阵',
      children: <RolesPanel data={data} onEdit={setRoleEditor} />,
    },
    {
      key: 'rooms',
      label: '直播间权限',
      children: <ResourcesPanel data={data} onEdit={setResourceEditor} />,
    },
    {
      key: 'groups',
      label: '飞书群范围',
      children: <GroupsPanel data={data} onEdit={setGroupEditor} />,
    },
  ]

  return (
    <Space orientation="vertical" size={16} className="page-stack">
      <Alert
        showIcon
        icon={<SafetyCertificateOutlined />}
        type="info"
        title="RBAC + Data Scope 已由后端统一执行"
        description="用户 → 角色 → 权限点 → 直播间范围。前端仅负责展示；跨直播间请求、详情和导出仍由 API 返回 403。个人自定义范围优先于角色范围。"
      />
      <Alert
        showIcon
        type="success"
        title="管理员可直接维护每个用户的网页账号与密码"
        description="新增用户时设置登录名和初始密码；已有用户可在“账号密码”中修改登录名或重置密码。飞书绑定、角色和直播间范围独立保存，不会被账号修改覆盖。"
      />
      <Card size="small">
        <Space wrap size={[8, 8]}>
          <Tag color="purple">{data.roles.length} 个角色</Tag>
          <Tag color="blue">{data.permissions.length} 个权限点</Tag>
          <Tag color="cyan">{data.room_resources.length} 个正式直播间资源</Tag>
          <Tag color="geekblue">{data.users.length} 个用户</Tag>
        </Space>
      </Card>
      <Tabs items={items} />
      <UserEditorModal
        value={userEditor}
        data={data}
        saving={saveUser.isPending}
        onCancel={() => setUserEditor(null)}
        onSave={(values) => saveUser.mutate(values)}
      />
      <CredentialsEditorModal
        value={credentialsEditor}
        saving={saveCredentials.isPending}
        onCancel={() => setCredentialsEditor(null)}
        onSave={(values) => saveCredentials.mutate(values)}
      />
      <RoleEditorModal
        value={roleEditor}
        data={data}
        saving={saveRole.isPending}
        onCancel={() => setRoleEditor(null)}
        onSave={(values) => saveRole.mutate(values)}
      />
      <ResourceEditorModal
        value={resourceEditor}
        saving={saveResource.isPending}
        onCancel={() => setResourceEditor(null)}
        onSave={(values) => saveResource.mutate(values)}
      />
      <GroupEditorModal
        value={groupEditor}
        data={data}
        saving={saveGroup.isPending}
        onCancel={() => setGroupEditor(null)}
        onSave={(values) => saveGroup.mutate(values)}
      />
    </Space>
  )
}

function UsersPanel({
  data,
  deletingUserId,
  onDelete,
  onEdit,
  onEditCredentials,
}: {
  data: PermissionOverview
  deletingUserId?: string
  onDelete: (userId: string) => void
  onEdit: (value: PermissionUser | 'new') => void
  onEditCredentials: (value: PermissionUser) => void
}) {
  return (
    <Space orientation="vertical" size={12} className="page-stack">
      <Space wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => onEdit('new')}>
          新增用户
        </Button>
        <Typography.Text type="secondary">
          “角色范围”随角色矩阵变化；“个人自定义”可覆盖为指定直播间或明确空范围。
        </Typography.Text>
      </Space>
      <Table<PermissionUser>
        rowKey="id"
        dataSource={data.users}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 1050 }}
        columns={[
          {
            title: '用户',
            width: 210,
            render: (_, item) => (
              <Space orientation="vertical" size={0}>
                <Typography.Text strong>{item.name}</Typography.Text>
                <Typography.Text type="secondary">
                  {item.username || item.email || '—'}
                </Typography.Text>
              </Space>
            ),
          },
          {
            title: '角色',
            dataIndex: 'role_codes',
            width: 250,
            render: (codes: string[]) => (
              <Space wrap size={[4, 4]}>
                {codes.map((code) => {
                  const role = data.roles.find((item) => item.role_code === code)
                  return (
                    <Tag key={code} color={roleColor[code]}>
                      {role?.role_name ?? code}
                    </Tag>
                  )
                })}
              </Space>
            ),
          },
          {
            title: '数据范围',
            width: 300,
            render: (_, item) => (
              <Space orientation="vertical" size={0}>
                <Typography.Text>{item.scope_label}</Typography.Text>
                <Typography.Text type="secondary">
                  {item.room_scope_mode === 'custom' ? '个人自定义范围' : '继承角色范围'}
                </Typography.Text>
              </Space>
            ),
          },
          {
            title: '登录方式',
            width: 180,
            render: (_, item) => (
              <Space orientation="vertical" size={0}>
                <Tag color={item.password_login_enabled ? 'blue' : 'default'}>
                  {item.password_login_enabled ? '网页账号已启用' : '网页账号未启用'}
                </Tag>
                <Tag color={item.feishu_bound ? 'green' : 'gold'}>
                  {item.feishu_bound ? '飞书已绑定' : '飞书未绑定'}
                </Tag>
                {item.last_login_at ? (
                  <Typography.Text type="secondary">
                    {new Date(item.last_login_at).toLocaleDateString('zh-CN')}
                  </Typography.Text>
                ) : null}
              </Space>
            ),
          },
          {
            title: '状态',
            width: 100,
            render: (_, item) => (
              <Tag color={item.active ? 'green' : 'default'}>{item.active ? '启用' : '停用'}</Tag>
            ),
          },
          {
            title: '操作',
            fixed: 'right',
            width: 300,
            render: (_, item) => (
              <Space size={4}>
                <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(item)}>
                  权限
                </Button>
                <Button size="small" icon={<KeyOutlined />} onClick={() => onEditCredentials(item)}>
                  账号密码
                </Button>
                <Popconfirm
                  title={`确认删除用户“${item.name}”？`}
                  description="账号和飞书绑定将立即失效；历史业务数据与审计记录会保留。"
                  okText="确认删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  disabled={item.id === data.current_actor}
                  onConfirm={() => onDelete(item.id)}
                >
                  <Button
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    disabled={item.id === data.current_actor}
                    loading={deletingUserId === item.id}
                    title={
                      item.id === data.current_actor ? '不能删除当前登录账号' : `删除${item.name}`
                    }
                  >
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  )
}

function RolesPanel({
  data,
  onEdit,
}: {
  data: PermissionOverview
  onEdit: (value: PermissionRole) => void
}) {
  return (
    <Table<PermissionRole>
      rowKey="id"
      dataSource={data.roles}
      pagination={false}
      scroll={{ x: 1100 }}
      columns={[
        {
          title: '角色',
          width: 220,
          render: (_, item) => (
            <Space orientation="vertical" size={0}>
              <Typography.Text strong>{item.role_name}</Typography.Text>
              <Typography.Text code>{item.role_code}</Typography.Text>
            </Space>
          ),
        },
        {
          title: '权限点',
          width: 360,
          render: (_, item) =>
            item.all_permissions ? (
              <Tag color="purple">ALL · 系统最高权限</Tag>
            ) : (
              <Space wrap size={[4, 4]}>
                {item.permission_codes.map((code) => (
                  <Tag key={code}>
                    {data.permissions.find((value) => value.code === code)?.name ?? code}
                  </Tag>
                ))}
              </Space>
            ),
        },
        {
          title: '直播间范围',
          width: 320,
          render: (_, item) =>
            item.all_permissions ? (
              <Tag color="purple">全部当前及未来直播间</Tag>
            ) : item.room_names.length ? (
              item.room_names.join('、')
            ) : (
              <Tag color="red">无直播间</Tag>
            ),
        },
        {
          title: '操作',
          fixed: 'right',
          width: 120,
          render: (_, item) => (
            <Button
              size="small"
              icon={<EditOutlined />}
              disabled={item.all_permissions}
              title={item.all_permissions ? '开发者 ALL 权限不可降级' : undefined}
              onClick={() => onEdit(item)}
            >
              配置
            </Button>
          ),
        },
      ]}
    />
  )
}

function ResourcesPanel({
  data,
  onEdit,
}: {
  data: PermissionOverview
  onEdit: (value: RoomResource) => void
}) {
  return (
    <Space orientation="vertical" size={12} className="page-stack">
      <Alert
        type="warning"
        showIcon
        title="权限使用正式直播间 UUID，不使用名称模糊匹配"
        description="产品分类和权限组用于种子回填及角色范围维护；停用资源后普通角色不能新增该直播间授权。"
      />
      <Table<RoomResource>
        rowKey="id"
        dataSource={data.room_resources}
        pagination={false}
        scroll={{ x: 'max-content' }}
        columns={[
          { title: '直播间', dataIndex: 'room_name' },
          {
            title: '产品分类',
            dataIndex: 'product_category',
            render: (value: string) => <Tag>{value}</Tag>,
          },
          {
            title: '权限组',
            dataIndex: 'permission_group',
            render: (value: string) => <Tag color="blue">{value}</Tag>,
          },
          {
            title: '状态',
            render: (_, item) => (
              <Tag color={item.enabled ? 'green' : 'default'}>{item.enabled ? '启用' : '停用'}</Tag>
            ),
          },
          {
            title: '操作',
            render: (_, item) => (
              <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(item)}>
                配置
              </Button>
            ),
          },
        ]}
      />
    </Space>
  )
}

function GroupsPanel({
  data,
  onEdit,
}: {
  data: PermissionOverview
  onEdit: (value: FeishuPermissionGroup | 'new') => void
}) {
  return (
    <Space orientation="vertical" size={12} className="page-stack">
      <Alert
        type="error"
        showIcon
        title="飞书推送按群直播间范围默认拒绝"
        description="每个目标群必须绑定正式直播间范围；群标识仅开发者可查看和配置。"
      />
      <Button type="primary" icon={<PlusOutlined />} onClick={() => onEdit('new')}>
        新增飞书群范围
      </Button>
      <Table<FeishuPermissionGroup>
        rowKey="id"
        dataSource={data.feishu_groups}
        locale={{ emptyText: '尚未配置飞书群范围；真实推送应保持关闭' }}
        pagination={false}
        scroll={{ x: 'max-content' }}
        columns={[
          { title: '群名称', dataIndex: 'name' },
          {
            title: '群标识',
            dataIndex: 'chat_id',
            render: (value: string) => `${value.slice(0, 6)}••••${value.slice(-4)}`,
          },
          {
            title: '允许直播间',
            dataIndex: 'room_names',
            render: (value: string[]) => value.join('、') || '无直播间',
          },
          {
            title: '状态',
            render: (_, item) => (
              <Tag color={item.enabled ? 'green' : 'default'}>{item.enabled ? '启用' : '停用'}</Tag>
            ),
          },
          {
            title: '操作',
            render: (_, item) => (
              <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(item)}>
                配置
              </Button>
            ),
          },
        ]}
      />
    </Space>
  )
}

function UserEditorModal({
  value,
  data,
  saving,
  onCancel,
  onSave,
}: {
  value: PermissionUser | 'new' | null
  data: PermissionOverview
  saving: boolean
  onCancel: () => void
  onSave: (values: UserFormValues) => void
}) {
  const [form] = Form.useForm<UserFormValues>()
  const scopeMode = Form.useWatch('room_scope_mode', form)
  const current = value === 'new' || value === null ? null : value
  return (
    <Modal
      open={value !== null}
      title={value === 'new' ? '新增用户' : `配置用户 · ${current?.name ?? ''}`}
      okText="保存权限"
      cancelText="取消"
      confirmLoading={saving}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.submit()}
      afterOpenChange={(open) => {
        if (!open) return
        form.setFieldsValue({
          username: current?.username ?? '',
          name: current?.name ?? '',
          email: current?.email ?? '',
          password: '',
          role_codes: current?.role_codes ?? [],
          room_scope_mode: current?.room_scope_mode ?? 'role',
          room_ids: current?.room_scope_mode === 'custom' ? (current.room_ids ?? []) : [],
          active: current?.active ?? true,
        })
      }}
    >
      <Form form={form} layout="vertical" onFinish={onSave}>
        {value === 'new' ? (
          <>
            <Form.Item name="username" label="登录名" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="email" label="邮箱（可选）" rules={[{ type: 'email' }]}>
              <Input />
            </Form.Item>
            <Form.Item
              name="password"
              label="初始密码"
              extra="至少 10 位；系统只保存单向哈希，保存后不会回显。"
              rules={[
                { required: true, message: '请输入初始密码' },
                { min: 10, message: '密码至少 10 位' },
                { max: 128, message: '密码最多 128 位' },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          </>
        ) : null}
        <Form.Item
          name="role_codes"
          label="角色"
          rules={[{ required: true, message: '至少选择一个角色' }]}
        >
          <Select
            mode="multiple"
            options={data.roles
              .filter((role) => role.active)
              .map((role) => ({ value: role.role_code, label: role.role_name }))}
          />
        </Form.Item>
        <Form.Item name="room_scope_mode" label="数据范围来源" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'role', label: '继承角色范围' },
              { value: 'custom', label: '个人自定义范围（优先）' },
            ]}
          />
        </Form.Item>
        {scopeMode === 'custom' ? (
          <Form.Item
            name="room_ids"
            label="个人允许直播间"
            extra="允许留空；留空表示明确禁止所有直播间。"
          >
            <Select
              mode="multiple"
              options={data.room_resources
                .filter((item) => item.enabled)
                .map((item) => ({ value: item.room_id, label: item.room_name }))}
            />
          </Form.Item>
        ) : null}
        <Form.Item name="active" label="账号启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function CredentialsEditorModal({
  value,
  saving,
  onCancel,
  onSave,
}: {
  value: PermissionUser | null
  saving: boolean
  onCancel: () => void
  onSave: (values: CredentialsFormValues) => void
}) {
  const [form] = Form.useForm<CredentialsFormValues>()
  return (
    <Modal
      open={value !== null}
      title={`账号与密码 · ${value?.name ?? ''}`}
      okText="保存账号设置"
      cancelText="取消"
      confirmLoading={saving}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.submit()}
      afterOpenChange={(open) => {
        if (!open) return
        form.setFieldsValue({
          username: value?.username ?? '',
          password: '',
          password_confirmation: '',
        })
      }}
    >
      <Alert
        type="info"
        showIcon
        title="可修改登录名，也可按需重置密码"
        description="新密码留空时只修改登录名，原密码保持不变；填写新密码后旧密码立即失效。飞书绑定、角色和数据范围不会改变。"
        style={{ marginBottom: 16 }}
      />
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item
          name="username"
          label="网页登录名"
          extra="登录名不区分大小写，保存时会去除首尾空格。"
          rules={[
            { required: true, message: '请输入网页登录名' },
            { min: 2, message: '登录名至少 2 位' },
            { max: 120, message: '登录名最多 120 位' },
          ]}
        >
          <Input autoComplete="username" />
        </Form.Item>
        <Form.Item
          name="password"
          label="新密码（可选）"
          extra="至少 10 位；留空表示保留原密码。系统只保存单向哈希，不会回显密码。"
          rules={[
            { min: 10, message: '密码至少 10 位' },
            { max: 128, message: '密码最多 128 位' },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="password_confirmation"
          label="确认新密码"
          dependencies={['password']}
          rules={[
            ({ getFieldValue }) => ({
              validator(_, input) {
                const password = getFieldValue('password') as string | undefined
                if (!password && !input) return Promise.resolve()
                if (!input) return Promise.reject(new Error('请再次输入新密码'))
                if (password === input) return Promise.resolve()
                return Promise.reject(new Error('两次输入的密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function RoleEditorModal({
  value,
  data,
  saving,
  onCancel,
  onSave,
}: {
  value: PermissionRole | null
  data: PermissionOverview
  saving: boolean
  onCancel: () => void
  onSave: (values: RoleFormValues) => void
}) {
  const [form] = Form.useForm<RoleFormValues>()
  return (
    <Modal
      open={value !== null}
      title={`配置角色 · ${value?.role_name ?? ''}`}
      okText="保存角色权限"
      cancelText="取消"
      confirmLoading={saving}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.submit()}
      afterOpenChange={(open) => {
        if (!open || !value) return
        form.setFieldsValue({
          role_name: value.role_name,
          description: value.description ?? '',
          permission_codes: value.permission_codes,
          room_ids: value.room_ids,
          active: value.active,
        })
      }}
    >
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item name="role_name" label="角色名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="description" label="角色说明">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="permission_codes" label="权限点">
          <Select
            mode="multiple"
            options={data.permissions.map((item) => ({
              value: item.code,
              label: `${item.name} · ${item.code}`,
            }))}
          />
        </Form.Item>
        <Form.Item name="room_ids" label="允许直播间">
          <Select
            mode="multiple"
            options={data.room_resources
              .filter((item) => item.enabled)
              .map((item) => ({ value: item.room_id, label: item.room_name }))}
          />
        </Form.Item>
        <Form.Item name="active" label="角色启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function ResourceEditorModal({
  value,
  saving,
  onCancel,
  onSave,
}: {
  value: RoomResource | null
  saving: boolean
  onCancel: () => void
  onSave: (values: ResourceFormValues) => void
}) {
  const [form] = Form.useForm<ResourceFormValues>()
  return (
    <Modal
      open={value !== null}
      title={`配置直播间 · ${value?.room_name ?? ''}`}
      okText="保存直播间权限"
      cancelText="取消"
      confirmLoading={saving}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.submit()}
      afterOpenChange={(open) => {
        if (!open || !value) return
        form.setFieldsValue({
          product_category: value.product_category,
          permission_group: value.permission_group,
          enabled: value.enabled,
        })
      }}
    >
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item name="product_category" label="产品分类" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="permission_group" label="权限组" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="enabled" label="资源启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function GroupEditorModal({
  value,
  data,
  saving,
  onCancel,
  onSave,
}: {
  value: FeishuPermissionGroup | 'new' | null
  data: PermissionOverview
  saving: boolean
  onCancel: () => void
  onSave: (values: GroupFormValues) => void
}) {
  const [form] = Form.useForm<GroupFormValues>()
  const current = value === 'new' || value === null ? null : value
  return (
    <Modal
      open={value !== null}
      title={value === 'new' ? '新增飞书群范围' : `配置飞书群 · ${current?.name ?? ''}`}
      okText="保存群范围"
      cancelText="取消"
      confirmLoading={saving}
      destroyOnHidden
      onCancel={onCancel}
      onOk={() => void form.submit()}
      afterOpenChange={(open) => {
        if (!open) return
        form.setFieldsValue({
          name: current?.name ?? '',
          chat_id: current?.chat_id ?? '',
          room_ids: current?.room_ids ?? [],
          enabled: current?.enabled ?? true,
        })
      }}
    >
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item name="name" label="群名称" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        {value === 'new' ? (
          <Form.Item name="chat_id" label="飞书群 Chat ID" rules={[{ required: true }]}>
            <Input.Password autoComplete="off" />
          </Form.Item>
        ) : (
          <Alert type="info" showIcon title="群标识创建后不可在此修改" />
        )}
        <Form.Item
          name="room_ids"
          label="允许接收的直播间"
          rules={[{ required: true, message: '至少绑定一个直播间' }]}
        >
          <Select
            mode="multiple"
            options={data.room_resources
              .filter((item) => item.enabled)
              .map((item) => ({ value: item.room_id, label: item.room_name }))}
          />
        </Form.Item>
        <Form.Item name="enabled" label="群配置启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  )
}
