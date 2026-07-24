import { expect, test } from '@playwright/test'
import path from 'node:path'

test('overview and natural-hour timeline are usable', async ({ page, request }) => {
  test.setTimeout(120_000)
  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: '经营总览', level: 3 })).toBeVisible()
  await expect(page.getByText('Excel 实际导出').first()).toBeVisible()
  await expect(page.locator('.kpi-card').first()).toBeVisible()

  const response = await request.get('/api/v1/charts/timeline', {
    params: { start_date: '2026-07-08', end_date: '2026-07-08', metric_keys: 'period_overall_roi' },
  })
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as {
    groups: Array<{ x_items: Array<{ label: string }> }>
  }
  expect(payload.groups[0]?.x_items[0]?.label).toMatch(/^\d{2}-\d{2}\n.+/)

  await page.getByRole('link', { name: '小时趋势' }).click()
  await expect(page.getByRole('heading', { name: '小时趋势', level: 3 })).toBeVisible()
  await page.getByText('合并系列', { exact: true }).click()
  await expect(page.getByText('直播间合并对比', { exact: true })).toBeVisible()
  await page.getByText('按直播间拆图', { exact: true }).click()
  const filteredRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return (
      url.pathname === '/api/v1/charts/timeline' &&
      url.searchParams.getAll('hour_slots').includes('08-09')
    )
  })
  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      url.pathname === '/api/v1/charts/timeline' &&
      url.searchParams.getAll('hour_slots').includes('08-09')
    )
  })
  const hourSelect = page.getByRole('combobox', { name: '自然小时' })
  await hourSelect.click()
  await hourSelect.fill('08-09')
  await hourSelect.press('Enter')
  const requestUrl = new URL((await filteredRequest).url())
  const filteredPayload = (await (await filteredResponse).json()) as {
    groups: Array<{ x_items: Array<{ hour_slot: string | null }> }>
  }
  expect(requestUrl.searchParams.getAll('hour_slots')).toEqual(['08-09'])
  expect(requestUrl.search).not.toContain('hour_slots%5B%5D')
  expect(filteredPayload.groups.flatMap((group) => group.x_items)).not.toHaveLength(0)
  expect(
    filteredPayload.groups.every((group) =>
      group.x_items.every((item) => item.hour_slot === '08-09'),
    ),
  ).toBeTruthy()
  await expect(page).toHaveURL(/hours=08-09/)
  await page.getByText('按月', { exact: true }).click()
  await expect(page.getByLabel('月份')).toHaveValue('2026-07')
  await expect(page).toHaveURL(/date_mode=month/)
  await expect(page.locator('canvas').first()).toBeVisible()
  await page.getByText('采集点', { exact: true }).click()
  await expect(page.getByText('真实采集点').first()).toBeVisible()

  const screenshot = path.resolve(process.cwd(), '../../artifacts/playwright-dashboard.png')
  await page.screenshot({ path: screenshot, fullPage: true })

  const defaultAnchorMetricsRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    const metrics = url.searchParams.getAll('metric_keys')
    return (
      url.pathname === '/api/v1/analytics/anchors/summary' &&
      metrics.length === 20 &&
      metrics[0] === 'period_gmv' &&
      metrics.at(-1) === 'period_net_order_cost' &&
      !metrics.includes('period_spend')
    )
  })
  await page.getByRole('link', { name: '主播分析' }).click()
  await defaultAnchorMetricsRequest
  await expect(page.getByRole('heading', { name: '主播分析', level: 3 })).toBeVisible()
  await expect(page.locator('.ant-table-row').first()).toBeVisible()
  await expect(page.getByText('已选 20 个指标')).toBeVisible()
  const anchorMetricRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return (
      url.pathname === '/api/v1/analytics/anchors/summary' &&
      url.searchParams.getAll('metric_keys').includes('period_buyers')
    )
  })
  await page.goto('/anchors?start=2026-07-17&end=2026-07-17&metrics=period_buyers')
  await anchorMetricRequest
  await expect(page.getByRole('columnheader', { name: /时段成交人数/ }).first()).toBeVisible()
  await expect(page.getByRole('columnheader', { name: /时均成交/ })).toBeVisible()
  const hourlyAverageAscending = page.getByRole('button', { name: '按时均成交升序' })
  await expect(hourlyAverageAscending).toBeVisible()
  await hourlyAverageAscending.click()
  await expect(hourlyAverageAscending).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('主播时段明细', { exact: true })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '自然小时' })).toBeVisible()
  await expect(page.getByText(/当前筛选范围共 \d+ 条时段数据/)).toBeVisible()
  await expect(page).toHaveURL(/metrics=period_buyers/)

  await page.getByRole('link', { name: '数据对比' }).click()
  await expect(page.getByRole('heading', { name: '数据对比', level: 3 })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: '是基准的' })).toBeVisible()

  await page.getByRole('link', { name: '主播场控透视' }).click()
  await expect(
    page.getByRole('heading', { name: '主播场控时间汇总透视表', level: 3 }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: /XLSX/ })).toBeVisible()

  const trendRuleResponse = await request.post('/api/v1/settings/hourly-comparison-rules', {
    data: {
      name: 'E2E主播3天趋势规则',
      rule_type: 'anchor_trend_summary',
      period_days: 3,
      spend_increase_threshold: 0.3,
      spend_decrease_threshold: -0.3,
      roi_increase_threshold: 0.3,
      roi_decrease_threshold: -0.3,
      minimum_spend: 0,
      minimum_orders: 0,
      minimum_coverage_rate: 0,
      minimum_effective_hours: 1,
      evaluation_delay_minutes: 0,
      push_schedule: 'manual',
      schedule_timezone: 'Asia/Shanghai',
      applicable_rooms: [],
      applicable_anchors: [],
      enabled: true,
      push_enabled: false,
      push_chat_id: null,
      send_rise: true,
      send_fall: true,
      rise_limit: 10,
      fall_limit: 10,
      send_empty_summary: false,
      allow_force_resend: true,
      push_retry_limit: 3,
      cooldown_minutes: 0,
    },
  })
  expect(trendRuleResponse.ok()).toBeTruthy()
  const trendRule = (await trendRuleResponse.json()) as { id: string }
  const trendRecalculation = await request.post('/api/v1/alerts/anchor-trends/recalculate', {
    data: {
      rule_id: trendRule.id,
      period_days: 3,
      end_date: '2026-07-17',
      room_ids: [],
      anchor_names: [],
    },
  })
  expect(trendRecalculation.ok()).toBeTruthy()
  const trendPayload = (await trendRecalculation.json()) as {
    summary: { rise_count: number; fall_count: number; insufficient_count: number }
  }
  expect(trendPayload.summary.rise_count).toBeGreaterThan(0)
  expect(trendPayload.summary.fall_count).toBeGreaterThan(0)

  await page.getByRole('link', { name: '预警中心', exact: true }).click()
  await expect(page.getByRole('heading', { name: '主播趋势预警中心', level: 3 })).toBeVisible()
  await expect(page.getByRole('tab', { name: /上涨榜/ })).toBeVisible()
  await expect(page.locator('.anchor-trend-row-rise').first()).toBeVisible()
  await page
    .locator('.anchor-trend-row-rise')
    .first()
    .getByRole('button', { name: /查看.*趋势详情/ })
    .click()
  await expect(page.getByRole('tab', { name: /逐日汇总/ })).toBeVisible()
  await page.getByRole('tab', { name: /24 小时明细/ }).click()
  await expect(page.getByText('00-01', { exact: true }).first()).toBeVisible()
  await page.locator('.ant-drawer-close').click()
  await page.getByRole('tab', { name: /样本不足/ }).click()
  await expect(page.locator('.anchor-trend-row-insufficient').first()).toBeVisible()
  await page.getByRole('tab', { name: /上涨榜/ }).click()
  await page.getByRole('button', { name: '测试上涨榜推送' }).click()
  await expect(page.getByText('Mock 测试卡片已生成')).toBeVisible()
  const trendScreenshot = path.resolve(
    process.cwd(),
    '../../artifacts/playwright-anchor-trends.png',
  )
  await page.screenshot({ path: trendScreenshot, fullPage: true })

  await page.getByRole('link', { name: '数据源管理' }).click()
  await expect(page.getByRole('heading', { name: '管理后台', level: 3 })).toBeVisible()
  await expect(page.getByRole('button', { name: '测试连接' }).first()).toBeVisible()
  await page.getByRole('button', { name: '扫描字段' }).first().click()
  await expect(page.getByText('操作完成')).toBeVisible()
  await page.getByRole('tab', { name: '系统设置' }).click()
  await expect(page.getByRole('row', { name: /飞书应用凭据 否 群机器人 否/ })).toBeVisible()
})
