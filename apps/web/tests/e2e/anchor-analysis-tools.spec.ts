import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const artifactRoot = path.resolve(process.cwd(), '../../artifacts/stage42')

function artifactPath(filename: string): string {
  fs.mkdirSync(artifactRoot, { recursive: true })
  return path.join(artifactRoot, filename)
}

test.describe.configure({ mode: 'serial' })

test('主播分析支持分组配置指标、下载时段表格和全屏查看', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/anchors')
  await expect(page.getByRole('heading', { name: '主播分析', level: 3 })).toBeVisible()
  await expect(page.locator('.analysis-summary-table')).toBeVisible()

  const metricTrigger = page.getByRole('button', { name: /配置指标，已选/ })
  await expect(metricTrigger).toBeVisible()
  await metricTrigger.click()

  const configurator = page.locator('.metric-config-modal .ant-modal')
  await expect(configurator).toBeVisible()
  await expect(configurator.getByText('流量人群', { exact: true })).toBeVisible()
  await expect(configurator.getByText('交易结果', { exact: true })).toBeVisible()
  await expect(configurator.getByText('转化效率', { exact: true })).toBeVisible()
  await expect(configurator.getByText('投放回报', { exact: true })).toBeVisible()
  await expect(configurator.getByLabel('搜索指标')).toBeVisible()
  await page.screenshot({
    path: artifactPath('anchor-metric-configurator.png'),
    fullPage: false,
  })
  await page.keyboard.press('Escape')
  await expect(configurator).toBeHidden()

  const downloadButton = page.getByRole('button', { name: '下载表格' }).first()
  const fullscreenButton = page.getByRole('button', { name: '全屏查看' })
  await expect(downloadButton).toBeEnabled()
  await expect(fullscreenButton).toBeEnabled()

  const [download] = await Promise.all([page.waitForEvent('download'), downloadButton.click()])
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/)

  await fullscreenButton.click()
  const fullscreen = page.locator('.anchor-hour-fullscreen-modal .ant-modal')
  await expect(fullscreen).toBeVisible()
  await expect(fullscreen.getByText('主播时段明细', { exact: true })).toBeVisible()
  await expect(fullscreen.getByRole('button', { name: '退出全屏' })).toBeVisible()
  await expect(fullscreen.locator('.ant-table')).toBeVisible()
  await page.screenshot({
    path: artifactPath('anchor-hour-detail-fullscreen.png'),
    fullPage: false,
  })

  await fullscreen.getByRole('button', { name: '退出全屏' }).click()
  await expect(fullscreen).toBeHidden()
})
