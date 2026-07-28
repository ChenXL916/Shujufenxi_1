import { ReloadOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons'
import { Button, Checkbox, Empty, Input, Modal, Tag } from 'antd'
import { useMemo, useState } from 'react'
import type { MetricOption } from '@/types/dashboard'

interface Props {
  metrics?: MetricOption[]
  value: string[]
  defaultMetricKeys: string[]
  onChange: (metricKeys: string[]) => void
}

const GROUPS: ReadonlyArray<{
  key: string
  label: string
  description: string
  categories: ReadonlySet<string>
}> = [
  {
    key: 'traffic',
    label: '流量人群',
    description: '观看、曝光、在线与成交人数',
    categories: new Set(['人数']),
  },
  {
    key: 'transaction',
    label: '交易结果',
    description: '成交金额、订单与客单成本',
    categories: new Set(['金额', '订单', '成本']),
  },
  {
    key: 'conversion',
    label: '转化效率',
    description: '从曝光到观看、点击与成交的效率',
    categories: new Set(['转化']),
  },
  {
    key: 'investment',
    label: '投放回报',
    description: '消耗、支付 ROI 与净 ROI',
    categories: new Set(['消耗', 'ROI']),
  },
]

function groupFor(metric: MetricOption): string {
  return GROUPS.find((group) => group.categories.has(metric.category))?.key ?? 'other'
}

export function MetricConfigurator({ metrics = [], value, defaultMetricKeys, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [pending, setPending] = useState<string[]>(value)
  const metricsByKey = useMemo(
    () => new Map(metrics.map((metric) => [metric.key, metric])),
    [metrics],
  )
  const selectedMetrics = value
    .map((key) => metricsByKey.get(key))
    .filter((metric) => metric !== undefined)
  const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')
  const filteredMetrics = useMemo(
    () =>
      metrics.filter(
        (metric) =>
          !normalizedQuery ||
          `${metric.name} ${metric.category} ${metric.scope}`
            .toLocaleLowerCase('zh-CN')
            .includes(normalizedQuery),
      ),
    [metrics, normalizedQuery],
  )
  const groupedMetrics = useMemo(
    () =>
      GROUPS.map((group) => ({
        ...group,
        metrics: filteredMetrics.filter((metric) => groupFor(metric) === group.key),
      })).filter((group) => group.metrics.length),
    [filteredMetrics],
  )
  const otherMetrics = filteredMetrics.filter((metric) => groupFor(metric) === 'other')

  const show = () => {
    setPending(value)
    setQuery('')
    setOpen(true)
  }
  const toggleMetric = (key: string, checked: boolean) => {
    setPending((current) =>
      checked
        ? metrics
            .filter((metric) => current.includes(metric.key) || metric.key === key)
            .map((metric) => metric.key)
        : current.filter((item) => item !== key),
    )
  }
  const restoreDefaults = () => {
    const available = new Set(metrics.map((metric) => metric.key))
    setPending(defaultMetricKeys.filter((key) => available.has(key)))
  }

  return (
    <>
      <Button
        className="metric-config-trigger"
        aria-label={`配置指标，已选 ${value.length} 个`}
        aria-expanded={open}
        onClick={show}
      >
        <span className="metric-config-trigger-title">
          <SettingOutlined aria-hidden="true" />
          <span>配置指标</span>
          <strong>{value.length}</strong>
        </span>
        <span className="metric-config-trigger-preview" aria-hidden="true">
          {selectedMetrics.slice(0, 2).map((metric) => (
            <span key={metric.key}>{metric.name}</span>
          ))}
          {selectedMetrics.length > 2 ? <b>+{selectedMetrics.length - 2}</b> : null}
        </span>
      </Button>
      <Modal
        open={open}
        width={920}
        rootClassName="metric-config-modal"
        title={
          <div className="metric-config-title">
            <span className="metric-config-title-icon" aria-hidden="true">
              <SettingOutlined />
            </span>
            <div>
              <strong>配置指标</strong>
              <span>按业务环节选择主播分析和时段明细要展示的数据</span>
            </div>
          </div>
        }
        onCancel={() => setOpen(false)}
        footer={
          <div className="metric-config-footer">
            <Button icon={<ReloadOutlined />} onClick={restoreDefaults}>
              恢复默认配置
            </Button>
            <div>
              <Button onClick={() => setOpen(false)}>取消</Button>
              <Button
                type="primary"
                disabled={!pending.length}
                onClick={() => {
                  onChange(pending)
                  setOpen(false)
                }}
              >
                应用 {pending.length} 个指标
              </Button>
            </div>
          </div>
        }
      >
        <div className="metric-config-toolbar">
          <div>
            <strong>已选择 {pending.length} 个</strong>
            <span>{pending.length ? '勾选结果将在两张表中同步生效' : '请至少选择 1 个指标'}</span>
          </div>
          <Input
            allowClear
            value={query}
            prefix={<SearchOutlined aria-hidden="true" />}
            placeholder="搜索指标名称或类型"
            aria-label="搜索指标"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        {pending.length ? (
          <div className="metric-config-selected" aria-label="已选指标摘要">
            {pending.slice(0, 8).map((key) => {
              const metric = metricsByKey.get(key)
              return metric ? <Tag key={key}>{metric.name}</Tag> : null
            })}
            {pending.length > 8 ? <Tag>另有 {pending.length - 8} 个</Tag> : null}
          </div>
        ) : null}
        {groupedMetrics.length || otherMetrics.length ? (
          <div className="metric-config-groups">
            {groupedMetrics.map((group) => (
              <section className="metric-config-group" key={group.key}>
                <header>
                  <div>
                    <strong>{group.label}</strong>
                    <span>{group.description}</span>
                  </div>
                  <Tag>{group.metrics.length} 项</Tag>
                </header>
                <div className="metric-config-options">
                  {group.metrics.map((metric) => {
                    const checked = pending.includes(metric.key)
                    return (
                      <label
                        key={metric.key}
                        className={`metric-config-option${checked ? ' is-selected' : ''}`}
                      >
                        <Checkbox
                          checked={checked}
                          onChange={(event) => toggleMetric(metric.key, event.target.checked)}
                        >
                          <span className="metric-config-option-copy">
                            <strong>{metric.name}</strong>
                            <small>
                              {metric.scope === 'period'
                                ? '时段值'
                                : metric.scope === 'derived'
                                  ? '计算指标'
                                  : metric.scope === 'instant'
                                    ? '即时值'
                                    : '累计值'}
                            </small>
                          </span>
                        </Checkbox>
                      </label>
                    )
                  })}
                </div>
              </section>
            ))}
            {otherMetrics.length ? (
              <section className="metric-config-group">
                <header>
                  <div>
                    <strong>其他指标</strong>
                    <span>尚未归入以上业务环节的指标</span>
                  </div>
                  <Tag>{otherMetrics.length} 项</Tag>
                </header>
                <div className="metric-config-options">
                  {otherMetrics.map((metric) => {
                    const checked = pending.includes(metric.key)
                    return (
                      <label
                        key={metric.key}
                        className={`metric-config-option${checked ? ' is-selected' : ''}`}
                      >
                        <Checkbox
                          checked={checked}
                          onChange={(event) => toggleMetric(metric.key, event.target.checked)}
                        >
                          <span className="metric-config-option-copy">
                            <strong>{metric.name}</strong>
                            <small>{metric.category}</small>
                          </span>
                        </Checkbox>
                      </label>
                    )
                  })}
                </div>
              </section>
            ) : null}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的指标" />
        )}
      </Modal>
    </>
  )
}
