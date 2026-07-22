import { EditOutlined, PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  message,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import {
  createFeishuPermissionGroup,
  createPermissionUser,
  getPermissionOverview,
  updateFeishuPermissionGroup,
  updatePermissionRole,
  updatePermissionUserAccess,
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
  role_codes: string[]
  room_scope_mode: 'role' | 'custom'
  room_ids: string[]
  active: boolean
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

export function PermissionManagement() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['admin', 'permissions', 'overview'],
    queryFn: getPermissionOverview,
  })
  const [userEditor, setUserEditor] = useState<PermissionUser | 'new' | null>(null)
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
          email: values.email,
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
      children: <UsersPanel data={data} onEdit={setUserEditor} />,
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
        title="同事先用飞书登录一次，再按账号分配权限"
        description="开启自动开户后，新同事首次登录会出现在下方用户列表。你可以给每个人分别设置直播主管、单直播间 PM、受限查看者，或用个人自定义范围精确选择直播间。"
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
  onEdit,
}: {
  data: PermissionOverview
  onEdit: (value: PermissionUser | 'new') => void
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
            title: '飞书登录',
            width: 130,
            render: (_, item) => (
              <Space orientation="vertical" size={0}>
                <Tag color={item.feishu_bound ? 'green' : 'gold'}>
                  {item.feishu_bound ? '已绑定' : '待首次登录'}
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
            width: 110,
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
            <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
              <Input />
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
