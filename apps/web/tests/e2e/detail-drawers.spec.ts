import { expect, test } from '@playwright/test'
import type { Locator } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const evidenceDir = path.resolve(process.cwd(), '../../docs/ui/evidence/after/states')

async function expectDrawerFitsViewport(drawer: Locator) {
  await expect
    .poll(
      async () =>
        drawer.evaluate((element) => {
          const rect = element.getBoundingClientRect()
          return rect.right <= window.innerWidth + 1
        }),
      { timeout: 2_000 },
    )
    .toBe(true)
  const geometry = await drawer.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return {
      left: rect.left,
      right: rect.right,
      width: rect.width,
      viewportWidth: window.innerWidth,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    }
  })
  expect(geometry.left).toBeGreaterThanOrEqual(-1)
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth + 1)
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth + 1)
}

test('三类业务详情使用统一信息层级并适配窄屏', async ({ page, request }) => {
  test.setTimeout(120_000)
  await fs.mkdir(evidenceDir, { recursive: true })
  await page.setViewportSize({ width: 600, height: 1200 })

  await page.goto('/overview?start=2026-07-17&end=2026-07-17')
  await expect(page.locator('.kpi-card').first()).toBeVisible()
  const hourlyDetailButton = page.getByRole('button', { name: /查看 .* 详情/ }).first()
  await hourlyDetailButton.scrollIntoViewIfNeeded()
  await hourlyDetailButton.click()
  const hourlyDrawer = page.getByRole('dialog', { name: /分时详情/ })
  await expect(hourlyDrawer).toBeVisible()
  await expect(hourlyDrawer.getByText('HOURLY COMPARISON')).toBeVisible()
  await expect(hourlyDrawer.getByRole('heading', { name: '核心表现' })).toBeVisible()
  await expect(hourlyDrawer.getByRole('heading', { name: '明细数据' })).toBeVisible()
  await expect(hourlyDrawer.locator('.detail-metric-tile')).toHaveCount(8)
  await expectDrawerFitsViewport(hourlyDrawer)
  await hourlyDrawer.screenshot({ path: path.join(evidenceDir, 'hourly-detail-600x1200.png') })
  await page.keyboard.press('Escape')
  await expect(hourlyDrawer).toBeHidden()

  await page.goto('/timeline?start=2026-07-17&end=2026-07-17')
  const pointSelect = page.getByRole('combobox', { name: /选择数据点打开详情/ }).first()
  await pointSelect.click()
  const firstPoint = page
    .locator('.ant-select-item-option:not(.ant-select-item-option-disabled)')
    .first()
  await expect(firstPoint).toBeVisible()
  await firstPoint.click()
  await page
    .getByRole('button', { name: /打开所选数据点详情/ })
    .first()
    .click()
  const pointDrawer = page.getByRole('dialog', { name: '数据点详情' })
  await expect(pointDrawer).toBeVisible()
  await expect(pointDrawer.getByText('LIVE DATA POINT')).toBeVisible()
  await expect(pointDrawer.getByRole('heading', { name: '标准化指标' })).toBeVisible()
  await expect(pointDrawer.locator('.detail-overview-card')).toBeVisible()
  await expectDrawerFitsViewport(pointDrawer)
  await pointDrawer.screenshot({ path: path.join(evidenceDir, 'data-point-detail-600x1200.png') })
  await page.keyboard.press('Escape')
  await expect(pointDrawer).toBeHidden()

  const ruleResponse = await request.post('/api/v1/settings/hourly-comparison-rules', {
    data: {
      name: `E2E 统一详情 ${Date.now()}`,
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
  expect(ruleResponse.ok()).toBeTruthy()
  const rule = (await ruleResponse.json()) as { id: string }
  const recalculation = await request.post('/api/v1/alerts/anchor-trends/recalculate', {
    data: {
      rule_id: rule.id,
      period_days: 3,
      end_date: '2026-07-17',
      room_ids: [],
      anchor_names: [],
    },
  })
  expect(recalculation.ok()).toBeTruthy()

  await page.goto('/alerts?tab=rise&period_days=3&end_date=2026-07-17')
  const trendDetailButton = page.getByRole('button', { name: /查看.*趋势详情/ }).first()
  await expect(trendDetailButton).toBeVisible()
  await trendDetailButton.click()
  const trendDrawer = page.getByRole('dialog', { name: /趋势事实详情/ })
  await expect(trendDrawer).toBeVisible()
  await expect(trendDrawer.getByText('ANCHOR TREND FACT')).toBeVisible()
  await expect(trendDrawer.getByRole('heading', { name: '经营对比' })).toBeVisible()
  await expect(trendDrawer.getByRole('heading', { name: '事实明细' })).toBeVisible()
  await expect(trendDrawer.locator('.detail-metric-tile')).toHaveCount(8)
  await expectDrawerFitsViewport(trendDrawer)
  await trendDrawer.screenshot({ path: path.join(evidenceDir, 'anchor-trend-detail-600x1200.png') })
})
