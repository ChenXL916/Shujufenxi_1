import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { createRoomMetricTarget, getRoomMetricTargets, updateRoomMetricTarget } from '@/api/client'
import type { RoomMetricTarget, RoomMetricTargetInput } from '@/types/hourlyComparison'

interface TargetFormValues {
  room_name?: string
  product_category?: string
  metric_code: string
  target_value: number
  effective_dates?: [Dayjs, Dayjs]
  enabled: boolean
}

export function RoomMetricTargetSettings() {
  const queryClient = useQueryClient()
  const [form] = Form.useForm<TargetFormValues>()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<RoomMetricTarget | null>(null)
  const targets = useQuery({ queryKey: ['room-metric-targets'], queryFn: getRoomMetricTargets })
  const save = useMutation({
    mutationFn: async (values: TargetFormValues) => {
      const payload: RoomMetricTargetInput = {
        room_id: editing?.room_id ?? null,
        room_name: values.room_name?.trim() || null,
        product_category: values.product_category?.trim() || null,
        metric_code: values.metric_code,
        target_value: values.target_value,
        effective_start_date: values.effective_dates?.[0].format('YYYY-MM-DD') ?? null,
        effective_end_date: values.effective_dates?.[1].format('YYYY-MM-DD') ?? null,
        enabled: values.enabled,
      }
      return editing ? updateRoomMetricTarget(editing.id, payload) : createRoomMetricTarget(payload)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['room-metric-targets'] })
      setOpen(false)
      setEditing(null)
      form.resetFields()
      void message.success('ROI目标已保存')
    },
    onError: () => void message.error('ROI目标保存失败，请检查权限或有效期'),
  })

  const edit = (target: RoomMetricTarget) => {
    setEditing(target)
    form.setFieldsValue({
      room_name: target.room_name ?? undefined,
      product_category: target.product_category ?? undefined,
      metric_code: target.metric_code,
      target_value: Number(target.target_value),
      effective_dates:
        target.effective_start_date && target.effective_end_date
          ? [dayjs(target.effective_start_date), dayjs(target.effective_end_date)]
          : undefined,
      enabled: target.enabled,
    })
    setOpen(true)
  }

  const columns: ColumnsType<RoomMetricTarget> = [
    {
      title: '直播间',
      dataIndex: 'room_name',
      render: (value: string | null) => value ?? '全品类配置',
    },
    {
      title: '产品品类',
      dataIndex: 'product_category',
      render: (value: string | null) => value ?? '—',
    },
    { title: '指标', dataIndex: 'metric_code' },
    {
      title: '目标值',
      dataIndex: 'target_value',
      align: 'right',
      render: (value: string | number) => Number(value).toFixed(2),
    },
    {
      title: '生效日期',
      render: (_, row) =>
        row.effective_start_date || row.effective_end_date
          ? `${row.effective_start_date ?? '不限'} 至 ${row.effective_end_date ?? '不限'}`
          : '长期有效',
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      render: (value: boolean) => (
        <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag>
      ),
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 190 },
    {
      title: '操作',
      fixed: 'right',
      width: 90,
      render: (_, row) => <Button onClick={() => edit(row)}>编辑</Button>,
    },
  ]

  return (
    <Space orientation="vertical" size={12} className="drawer-stack">
      <div className="settings-section-heading">
        <div>
          <strong>直播间 ROI 目标</strong>
          <div className="settings-description">
            匹配优先级：直播间ID、直播间名称、产品品类；多目标不计算简单平均。
          </div>
        </div>
        <Button
          type="primary"
          onClick={() => {
            setEditing(null)
            form.setFieldsValue({ metric_code: 'period_overall_roi', enabled: true })
            setOpen(true)
          }}
        >
          新增目标
        </Button>
      </div>
      {targets.isError ? (
        <Alert
          type="error"
          showIcon
          title="ROI目标配置加载失败"
          action={<Button onClick={() => void targets.refetch()}>重试</Button>}
        />
      ) : (
        <Table<RoomMetricTarget>
          rowKey="id"
          size="small"
          loading={targets.isLoading}
          dataSource={targets.data ?? []}
          columns={columns}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1100 }}
        />
      )}
      <Modal
        open={open}
        title={editing ? '编辑 ROI 目标' : '新增 ROI 目标'}
        okText="保存"
        cancelText="取消"
        confirmLoading={save.isPending}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
          form.resetFields()
        }}
        onOk={() => void form.submit()}
        destroyOnHidden
      >
        <Form<TargetFormValues>
          form={form}
          layout="vertical"
          initialValues={{ metric_code: 'period_overall_roi', enabled: true }}
          onFinish={(values) => save.mutate(values)}
        >
          <Form.Item label="直播间精确名称" name="room_name">
            <Input placeholder="例如：柏瑞美-散粉" />
          </Form.Item>
          <Form.Item label="产品品类" name="product_category">
            <Input placeholder="例如：散粉；名称兜底时水散粉优先" />
          </Form.Item>
          <Form.Item label="指标" name="metric_code" rules={[{ required: true }]}>
            <Input disabled />
          </Form.Item>
          <Form.Item
            label="目标值"
            name="target_value"
            rules={[{ required: true, message: '请输入ROI目标值' }]}
          >
            <InputNumber min={0.01} step={0.01} precision={2} className="full-width" />
          </Form.Item>
          <Form.Item label="有效期" name="effective_dates">
            <DatePicker.RangePicker className="full-width" />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
