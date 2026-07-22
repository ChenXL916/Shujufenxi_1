import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import {
  createHourlyComparisonRule,
  getHourlyComparisonRules,
  updateHourlyComparisonRule,
} from '@/api/client'
import type {
  HourlyComparisonRule,
  HourlyComparisonRuleInput,
  HourlyComparisonRuleType,
} from '@/types/hourlyComparison'

type PeriodDays = HourlyComparisonRuleInput['period_days']

interface RuleFormValues {
  name: string
  rule_type: HourlyComparisonRuleType
  period_days: PeriodDays
  spend_increase_threshold: number
  spend_decrease_threshold: number
  roi_increase_threshold: number
  roi_decrease_threshold: number
  minimum_spend: number
  minimum_orders: number
  minimum_coverage_rate: number
  minimum_effective_hours: number
  evaluation_delay_minutes: number
  push_schedule: string
  schedule_timezone: 'Asia/Shanghai'
  applicable_rooms?: string
  applicable_anchors?: string
  enabled: boolean
  push_enabled: boolean
  push_chat_id?: string
  send_rise: boolean
  send_fall: boolean
  rise_limit: number
  fall_limit: number
  send_empty_summary: boolean
  allow_force_resend: boolean
  push_retry_limit: number
  cooldown_minutes: number
}

const PERIOD_OPTIONS: Array<{ label: string; value: PeriodDays }> = [1, 3, 5, 7, 15, 30].map(
  (value) => ({ label: `${value}天`, value: value as PeriodDays }),
)

const TYPE_OPTIONS: Array<{ label: string; value: HourlyComparisonRuleType }> = [
  { label: '主播趋势汇总', value: 'anchor_trend_summary' },
  { label: '旧版小时比较', value: 'hourly_comparison_legacy' },
]

const DEFAULT_VALUES: RuleFormValues = {
  name: '',
  rule_type: 'anchor_trend_summary',
  period_days: 3,
  spend_increase_threshold: 0.3,
  spend_decrease_threshold: -0.3,
  roi_increase_threshold: 0.3,
  roi_decrease_threshold: -0.3,
  minimum_spend: 0,
  minimum_orders: 0,
  minimum_coverage_rate: 0.8,
  minimum_effective_hours: 3,
  evaluation_delay_minutes: 15,
  push_schedule: 'daily@09:30',
  schedule_timezone: 'Asia/Shanghai',
  enabled: true,
  push_enabled: false,
  send_rise: true,
  send_fall: true,
  rise_limit: 10,
  fall_limit: 10,
  send_empty_summary: false,
  allow_force_resend: true,
  push_retry_limit: 3,
  cooldown_minutes: 60,
}

function commaList(value?: string): string[] {
  return (value ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function scheduleLabel(value: string): string {
  if (value === 'manual') return '仅手动'
  const daily = /^daily@(\d{2}:\d{2})$/.exec(value)
  if (daily) return `每天 ${daily[1]}`
  const weekly = /^weekly:([1-7])@(\d{2}:\d{2})$/.exec(value)
  if (weekly) {
    const names = ['一', '二', '三', '四', '五', '六', '日']
    return `每周${names[Number(weekly[1]) - 1]} ${weekly[2]}`
  }
  return value
}

function typeLabel(value: HourlyComparisonRuleType): string {
  return value === 'anchor_trend_summary' ? '主播趋势汇总' : '旧版小时比较'
}

export function HourlyComparisonRuleSettings() {
  const queryClient = useQueryClient()
  const [form] = Form.useForm<RuleFormValues>()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<HourlyComparisonRule | null>(null)
  const rules = useQuery({
    queryKey: ['hourly-comparison-rules'],
    queryFn: getHourlyComparisonRules,
  })
  const save = useMutation({
    mutationFn: async (values: RuleFormValues) => {
      const payload: HourlyComparisonRuleInput = {
        name: values.name.trim(),
        rule_type: values.rule_type,
        period_days: values.period_days,
        spend_increase_threshold: values.spend_increase_threshold,
        spend_decrease_threshold: values.spend_decrease_threshold,
        roi_increase_threshold: values.roi_increase_threshold,
        roi_decrease_threshold: values.roi_decrease_threshold,
        minimum_spend: values.minimum_spend,
        minimum_orders: values.minimum_orders,
        minimum_coverage_rate: values.minimum_coverage_rate,
        minimum_effective_hours: values.minimum_effective_hours,
        evaluation_delay_minutes: values.evaluation_delay_minutes,
        push_schedule: values.push_schedule.trim(),
        schedule_timezone: values.schedule_timezone,
        applicable_rooms: commaList(values.applicable_rooms),
        applicable_anchors: commaList(values.applicable_anchors),
        enabled: values.enabled,
        push_enabled: values.push_enabled,
        push_chat_id: values.push_chat_id?.trim() || null,
        send_rise: values.send_rise,
        send_fall: values.send_fall,
        rise_limit: values.rise_limit,
        fall_limit: values.fall_limit,
        send_empty_summary: values.send_empty_summary,
        allow_force_resend: values.allow_force_resend,
        push_retry_limit: values.push_retry_limit,
        cooldown_minutes: values.cooldown_minutes,
      }
      return editing
        ? updateHourlyComparisonRule(editing.id, payload)
        : createHourlyComparisonRule(payload)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['hourly-comparison-rules'] })
      form.resetFields()
      setOpen(false)
      setEditing(null)
      void message.success('预警规则已保存')
    },
    onError: () => void message.error('规则保存失败，请检查名称、周期、推送计划和阈值范围'),
  })

  const edit = (rule: HourlyComparisonRule) => {
    setEditing(rule)
    form.setFieldsValue({
      name: rule.name,
      rule_type: rule.rule_type ?? 'hourly_comparison_legacy',
      period_days: rule.period_days,
      spend_increase_threshold: Number(rule.spend_increase_threshold),
      spend_decrease_threshold: Number(rule.spend_decrease_threshold ?? -0.3),
      roi_increase_threshold: Number(rule.roi_increase_threshold),
      roi_decrease_threshold: Number(rule.roi_decrease_threshold),
      minimum_spend: Number(rule.minimum_spend),
      minimum_orders: rule.minimum_orders,
      minimum_coverage_rate: Number(rule.minimum_coverage_rate),
      minimum_effective_hours: rule.minimum_effective_hours ?? 1,
      evaluation_delay_minutes: rule.evaluation_delay_minutes,
      push_schedule: rule.push_schedule ?? 'manual',
      schedule_timezone: rule.schedule_timezone ?? 'Asia/Shanghai',
      applicable_rooms: rule.applicable_rooms.join(', '),
      applicable_anchors: (rule.applicable_anchors ?? []).join(', '),
      enabled: rule.enabled,
      push_enabled: rule.push_enabled,
      push_chat_id: rule.push_chat_id ?? undefined,
      send_rise: rule.send_rise ?? true,
      send_fall: rule.send_fall ?? true,
      rise_limit: rule.rise_limit ?? 10,
      fall_limit: rule.fall_limit ?? 10,
      send_empty_summary: rule.send_empty_summary ?? false,
      allow_force_resend: rule.allow_force_resend ?? true,
      push_retry_limit: rule.push_retry_limit ?? 3,
      cooldown_minutes: rule.cooldown_minutes ?? 60,
    })
    setOpen(true)
  }

  const columns: ColumnsType<HourlyComparisonRule> = [
    { title: '规则', dataIndex: 'name', width: 180, fixed: 'left' },
    {
      title: '类型',
      dataIndex: 'rule_type',
      width: 115,
      render: (value: HourlyComparisonRuleType) => (
        <Tag color={value === 'anchor_trend_summary' ? 'blue' : 'default'}>{typeLabel(value)}</Tag>
      ),
    },
    { title: '周期', dataIndex: 'period_days', width: 55, render: (value: number) => `${value}天` },
    {
      title: 'ROI上涨 / 下降',
      width: 125,
      render: (_, row) =>
        `${(Number(row.roi_increase_threshold) * 100).toFixed(0)}% / ${(Number(row.roi_decrease_threshold) * 100).toFixed(0)}%`,
    },
    {
      title: '最低完整率',
      dataIndex: 'minimum_coverage_rate',
      width: 90,
      render: (value: string | number) => `${(Number(value) * 100).toFixed(0)}%`,
    },
    {
      title: '最小有效小时',
      dataIndex: 'minimum_effective_hours',
      width: 100,
      render: (value: number) => `${value}小时`,
    },
    {
      title: '推送计划',
      dataIndex: 'push_schedule',
      width: 115,
      render: scheduleLabel,
    },
    {
      title: '上涨 / 下跌榜人数',
      width: 120,
      render: (_, row) => `${row.rise_limit} / ${row.fall_limit}`,
    },
    {
      title: '页面 / 推送',
      width: 130,
      render: (_, row) => (
        <Space size={4} wrap>
          <Tag color={row.enabled ? 'success' : 'default'}>{row.enabled ? '启用' : '停用'}</Tag>
          <Tag color={row.push_enabled ? 'blue' : 'default'}>
            {row.push_enabled ? '飞书开启' : '仅页面'}
          </Tag>
        </Space>
      ),
    },
    {
      title: '操作',
      fixed: 'right',
      width: 75,
      render: (_, row) => <Button onClick={() => edit(row)}>编辑</Button>,
    },
  ]

  return (
    <Space orientation="vertical" size={12} className="drawer-stack">
      <div className="settings-section-heading">
        <div>
          <strong>主播趋势与小时比较预警规则</strong>
          <div className="settings-description">
            同一规则承载趋势判断、样本门槛、榜单人数、定时计划和重发审计；编辑时锁定既有类型，避免旧规则被静默转换。
          </div>
        </div>
        <Button
          type="primary"
          onClick={() => {
            setEditing(null)
            form.setFieldsValue(DEFAULT_VALUES)
            setOpen(true)
          }}
        >
          新增预警规则
        </Button>
      </div>
      {rules.isError ? (
        <Alert
          type="error"
          showIcon
          title="预警规则加载失败或当前账号无权查看"
          action={<Button onClick={() => void rules.refetch()}>重试</Button>}
        />
      ) : (
        <Table<HourlyComparisonRule>
          rowKey="id"
          size="small"
          loading={rules.isLoading}
          dataSource={rules.data ?? []}
          columns={columns}
          pagination={false}
          scroll={{ x: 1105 }}
        />
      )}
      <Modal
        open={open}
        title={editing ? '编辑预警规则' : '新增预警规则'}
        okText="保存"
        cancelText="取消"
        width={920}
        confirmLoading={save.isPending}
        forceRender
        onCancel={() => {
          form.resetFields()
          setOpen(false)
          setEditing(null)
        }}
        onOk={() => void form.submit()}
      >
        <Form<RuleFormValues>
          form={form}
          layout="vertical"
          initialValues={DEFAULT_VALUES}
          onFinish={(values) => save.mutate(values)}
          className="alert-rule-form"
        >
          <Alert
            type="info"
            showIcon
            title={
              editing
                ? '规则类型和周期已锁定；保存不会把旧版小时规则转换为主播趋势规则。'
                : '新增规则默认使用主播趋势汇总类型，可在首次保存前切换。'
            }
          />
          <Typography.Title level={5}>基础与判断门槛</Typography.Title>
          <div className="alert-rule-form-grid">
            <Form.Item
              className="alert-rule-form-span-2"
              label="规则名称"
              name="name"
              rules={[{ required: true, whitespace: true, message: '请输入规则名称' }]}
            >
              <Input maxLength={200} />
            </Form.Item>
            <Form.Item label="规则类型" name="rule_type" rules={[{ required: true }]}>
              <Select aria-label="规则类型" options={TYPE_OPTIONS} disabled={Boolean(editing)} />
            </Form.Item>
            <Form.Item label="周期" name="period_days" rules={[{ required: true }]}>
              <Select aria-label="周期" options={PERIOD_OPTIONS} disabled={Boolean(editing)} />
            </Form.Item>
            <Form.Item
              label="消耗上涨阈值"
              name="spend_increase_threshold"
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={10} step={0.05} className="full-width" />
            </Form.Item>
            <Form.Item
              label="消耗下降阈值"
              name="spend_decrease_threshold"
              rules={[{ required: true }]}
            >
              <InputNumber min={-10} max={0} step={0.05} className="full-width" />
            </Form.Item>
            <Form.Item
              label="ROI上涨阈值"
              name="roi_increase_threshold"
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={10} step={0.05} className="full-width" />
            </Form.Item>
            <Form.Item
              label="ROI下降阈值"
              name="roi_decrease_threshold"
              rules={[{ required: true }]}
            >
              <InputNumber min={-10} max={0} step={0.05} className="full-width" />
            </Form.Item>
            <Form.Item label="最小消耗" name="minimum_spend" rules={[{ required: true }]}>
              <InputNumber min={0} precision={2} className="full-width" />
            </Form.Item>
            <Form.Item label="最小订单数" name="minimum_orders" rules={[{ required: true }]}>
              <InputNumber min={0} precision={0} className="full-width" />
            </Form.Item>
            <Form.Item label="最低完整率" name="minimum_coverage_rate" rules={[{ required: true }]}>
              <InputNumber min={0} max={1} step={0.05} className="full-width" />
            </Form.Item>
            <Form.Item
              label="最小有效小时"
              name="minimum_effective_hours"
              rules={[{ required: true }]}
            >
              <InputNumber min={1} max={720} precision={0} className="full-width" />
            </Form.Item>
            <Form.Item
              label="小时结束后延迟（分钟）"
              name="evaluation_delay_minutes"
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={1440} precision={0} className="full-width" />
            </Form.Item>
            <Form.Item
              label="冷却时间（分钟）"
              name="cooldown_minutes"
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={1440} precision={0} className="full-width" />
            </Form.Item>
          </div>

          <Divider />
          <Typography.Title level={5}>适用范围</Typography.Title>
          <div className="alert-rule-form-grid">
            <Form.Item
              className="alert-rule-form-span-2"
              label="适用直播间 ID 或精确名称（逗号分隔）"
              name="applicable_rooms"
            >
              <Input placeholder="留空表示全部授权直播间" />
            </Form.Item>
            <Form.Item
              className="alert-rule-form-span-2"
              label="适用主播精确名称（逗号分隔）"
              name="applicable_anchors"
            >
              <Input placeholder="留空表示全部主播" />
            </Form.Item>
          </div>

          <Divider />
          <Typography.Title level={5}>飞书计划与发送策略</Typography.Title>
          <Alert
            type="warning"
            showIcon
            title="计划格式：manual、daily@HH:mm 或 weekly:1-7@HH:mm；业务时区固定为 Asia/Shanghai。"
          />
          <div className="alert-rule-form-grid alert-rule-form-grid-spaced">
            <Form.Item
              className="alert-rule-form-span-2"
              label="推送计划"
              name="push_schedule"
              rules={[
                { required: true, whitespace: true, message: '请输入推送计划' },
                {
                  pattern:
                    /^(manual|daily@(?:[01]\d|2[0-3]):[0-5]\d|weekly:[1-7]@(?:[01]\d|2[0-3]):[0-5]\d)$/,
                  message: '请输入 manual、daily@HH:mm 或 weekly:1-7@HH:mm',
                },
              ]}
            >
              <Input placeholder="daily@09:30" />
            </Form.Item>
            <Form.Item label="计划时区" name="schedule_timezone" rules={[{ required: true }]}>
              <Select
                aria-label="计划时区"
                options={[{ label: 'Asia/Shanghai', value: 'Asia/Shanghai' }]}
                disabled
              />
            </Form.Item>
            <Form.Item label="推送重试上限" name="push_retry_limit" rules={[{ required: true }]}>
              <InputNumber min={1} max={10} precision={0} className="full-width" />
            </Form.Item>
            <Form.Item label="上涨榜最多人数" name="rise_limit" rules={[{ required: true }]}>
              <InputNumber min={1} max={100} precision={0} className="full-width" />
            </Form.Item>
            <Form.Item label="下跌榜最多人数" name="fall_limit" rules={[{ required: true }]}>
              <InputNumber min={1} max={100} precision={0} className="full-width" />
            </Form.Item>
            <Form.Item
              className="alert-rule-form-span-2"
              label="目标飞书群 ID（可选）"
              name="push_chat_id"
            >
              <Input.Password
                autoComplete="new-password"
                placeholder="oc_xxx；留空使用系统默认群"
              />
            </Form.Item>
          </div>
          <div className="alert-rule-switch-grid">
            <Form.Item label="启用页面判断" name="enabled" valuePropName="checked">
              <Switch aria-label="启用页面判断" />
            </Form.Item>
            <Form.Item label="启用飞书推送" name="push_enabled" valuePropName="checked">
              <Switch aria-label="启用飞书推送" />
            </Form.Item>
            <Form.Item label="发送上涨榜" name="send_rise" valuePropName="checked">
              <Switch aria-label="发送上涨榜" />
            </Form.Item>
            <Form.Item label="发送下跌榜" name="send_fall" valuePropName="checked">
              <Switch aria-label="发送下跌榜" />
            </Form.Item>
            <Form.Item label="空榜也发送摘要" name="send_empty_summary" valuePropName="checked">
              <Switch aria-label="空榜也发送摘要" />
            </Form.Item>
            <Form.Item label="允许强制重发" name="allow_force_resend" valuePropName="checked">
              <Switch aria-label="允许强制重发" />
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </Space>
  )
}
