import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const artifactRoot = path.resolve(process.cwd(), '../../artifacts/stage44')

function artifactPath(filename: string): string {
  fs.mkdirSync(artifactRoot, { recursive: true })
  return path.join(artifactRoot, filename)
}

test.describe.configure({ mode: 'serial' })

test('全站指标筛选统一使用配置指标并保持页面数据联动', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const pageErrors: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  for (const target of [
    { route: '/timeline', heading: '小时趋势' },
    { route: '/comparison', heading: '数据对比' },
    { route: '/anchors', heading: '主播分析' },
    { route: '/controls', heading: '场控分析' },
    { route: '/pairings', heading: '主播 × 场控搭配' },
  ]) {
    await page.goto(target.route)
    await expect(page.getByRole('heading', { name: target.heading, level: 3 })).toBeVisible()
    await expect(page.locator('.metric-select')).toHaveCount(0)

    const trigger = page.getByRole('button', { name: /配置指标，已选/ })
    await expect(trigger).toBeVisible()
    await expect(trigger).toBeEnabled()
    await trigger.click()

    const configurator = page.locator('.metric-config-modal .ant-modal')
    await expect(configurator).toBeVisible()
    await expect
      .poll(async () => (await configurator.boundingBox())?.width ?? 0)
      .toBeGreaterThan(880)
    await page.waitForTimeout(350)
    await expect(configurator.getByText('流量人群', { exact: true })).toBeVisible()
    await expect(configurator.getByText('交易结果', { exact: true })).toBeVisible()
    await expect(configurator.getByText('转化效率', { exact: true })).toBeVisible()
    await expect(configurator.getByText('投放回报', { exact: true })).toBeVisible()
    if (target.route === '/timeline') {
      await page.screenshot({
        path: artifactPath('timeline-metric-configurator-desktop.png'),
        fullPage: false,
      })
    }

    await page.keyboard.press('Escape')
    await expect(configurator).toBeHidden()
  }

  await page.goto('/timeline?start=2026-07-17&end=2026-07-17&metrics=period_overall_amount')
  await expect(page.getByRole('heading', { name: '小时趋势', level: 3 })).toBeVisible()
  const timelineTrigger = page.getByRole('button', { name: '配置指标，已选 1 个' })
  await timelineTrigger.click()
  const buyers = page.getByRole('checkbox', { name: /时段成交人数/ })
  await buyers.check()
  const timelineRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return (
      url.pathname === '/api/v1/charts/timeline' &&
      url.searchParams.getAll('metric_keys').includes('period_buyers')
    )
  })
  await page.getByRole('button', { name: '应用 2 个指标' }).click()
  await timelineRequest
  await expect(page).toHaveURL(/metrics=period_overall_amount%2Cperiod_buyers/)

  expect(pageErrors).toEqual([])
  expect(consoleErrors).toEqual([])
})

test('24小时对比配置保留核心指标和最多四项约束', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const pageErrors: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: '经营总览', level: 3 })).toBeVisible()

  const trigger = page.getByRole('button', { name: '配置指标，已选 2 个' })
  await expect(trigger).toBeVisible()
  await trigger.click()

  const configurator = page.locator('.metric-config-modal .ant-modal')
  await expect(configurator).toBeVisible()
  await expect.poll(async () => (await configurator.boundingBox())?.width ?? 0).toBeGreaterThan(880)
  await page.waitForTimeout(350)
  await expect(configurator.getByText(/最多选择 4 个/)).toBeVisible()
  await page.screenshot({
    path: artifactPath('overview-hourly-metric-configurator-desktop.png'),
    fullPage: false,
  })
  await expect(configurator.getByRole('checkbox', { name: /时段整体支付ROI/ })).toBeDisabled()
  await expect(configurator.getByRole('checkbox', { name: /时段消耗/ })).toBeDisabled()
  expect(pageErrors).toEqual([])
  expect(consoleErrors).toEqual([])
})

test('移动端在更多筛选中可完整打开配置指标', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const pageErrors: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  await page.goto('/timeline')
  await expect(page.getByRole('heading', { name: '小时趋势', level: 3 })).toBeVisible()
  await page.getByRole('button', { name: /打开更多筛选/ }).click()
  await expect(page.getByRole('dialog', { name: '更多筛选' })).toBeVisible()

  await page.getByRole('button', { name: /配置指标，已选/ }).click()
  const configurator = page.locator('.metric-config-modal .ant-modal')
  await expect(configurator).toBeVisible()
  await expect.poll(async () => (await configurator.boundingBox())?.width ?? 0).toBeGreaterThan(340)
  await page.waitForTimeout(350)
  const box = await configurator.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.width).toBeLessThanOrEqual(366)
  expect(box!.x).toBeGreaterThanOrEqual(0)

  await page.screenshot({
    path: artifactPath('timeline-metric-configurator-mobile.png'),
    fullPage: false,
  })
  expect(pageErrors).toEqual([])
  expect(consoleErrors).toEqual([])
})
