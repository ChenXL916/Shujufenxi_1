import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const artifactRoot = path.resolve(process.cwd(), '../../artifacts/index-redesign/after')

const forbiddenDarkSurfaces = new Set([
  'rgb(7, 7, 10)',
  'rgb(9, 10, 15)',
  'rgb(13, 15, 20)',
  'rgb(18, 20, 27)',
  'rgb(23, 26, 34)',
  'rgb(32, 35, 45)',
  'rgb(41, 45, 57)',
  'rgb(57, 62, 78)',
])

function artifactPath(...parts: string[]): string {
  const file = path.join(artifactRoot, ...parts)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  return file
}

async function waitForDashboard(page: import('@playwright/test').Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded')
  await page.locator('.app-shell').waitFor({ state: 'visible' })
  await page.waitForTimeout(600)
}

async function expectNoPageOverflow(page: import('@playwright/test').Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    documentScrollWidth: document.documentElement.scrollWidth,
    documentClientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    viewportWidth: window.innerWidth,
  }))
  expect(dimensions.documentScrollWidth, JSON.stringify(dimensions)).toBe(
    dimensions.documentClientWidth,
  )
  expect(dimensions.bodyScrollWidth, JSON.stringify(dimensions)).toBeLessThanOrEqual(
    dimensions.viewportWidth,
  )
}

async function expectNamedButtons(page: import('@playwright/test').Page): Promise<void> {
  const unnamed = await page.locator('button:visible').evaluateAll((buttons) =>
    buttons
      .filter((button) => {
        const label = button.getAttribute('aria-label')?.trim()
        const title = button.getAttribute('title')?.trim()
        const text = button.textContent?.trim()
        const descendantLabel = button
          .querySelector('[aria-label]')
          ?.getAttribute('aria-label')
          ?.trim()
        return !label && !title && !text && !descendantLabel
      })
      .map((button) => button.outerHTML.slice(0, 180)),
  )
  expect(unnamed).toEqual([])
}

async function expectWarmTheme(
  page: import('@playwright/test').Page,
  viewportWidth: number,
): Promise<void> {
  const theme = await page.evaluate(() => {
    const card = document.querySelector(
      '.kpi-card, .data-card, .chart-card, .pivot-card, .hourly-comparison-card, .ant-card',
    )
    const heading = document.querySelector('.page-heading h3') as HTMLElement
    const sider = document.querySelector('.app-sider')
    const sampled = Array.from(
      document.querySelectorAll<HTMLElement>(
        '.app-shell, .app-sider, .app-header, .filter-bar, .kpi-card, .data-card, .hourly-comparison-card, .ant-table',
      ),
    ).map((element) => ({
      className: element.className,
      background: getComputedStyle(element).backgroundColor,
    }))
    return {
      name: document.querySelector('.app-shell')?.getAttribute('data-theme'),
      colorScheme: getComputedStyle(document.documentElement).colorScheme,
      orangeSoft: getComputedStyle(document.documentElement)
        .getPropertyValue('--color-accent-orange-soft')
        .trim(),
      body: getComputedStyle(document.body).backgroundColor,
      card: card ? getComputedStyle(card).backgroundColor : null,
      heading: getComputedStyle(heading).color,
      sider: sider ? getComputedStyle(sider).backgroundColor : null,
      sampled,
    }
  })

  expect(theme.name).toBe('index-warm-bi')
  expect(theme.colorScheme).toBe('light')
  expect(theme.orangeSoft).not.toBe('')
  expect(theme.orangeSoft).not.toContain('var(--color-accent-orange-soft)')
  expect(theme.body).toBe('rgb(247, 246, 242)')
  expect(theme.card).toBe('rgb(255, 255, 255)')
  expect(theme.heading).toBe('rgb(23, 23, 22)')
  expect(await page.locator('.ant-menu-dark').count()).toBe(0)
  if (viewportWidth >= 992) {
    expect(await page.locator('.ant-menu-light').count()).toBeGreaterThan(0)
    expect(theme.sider).toBe('rgb(251, 250, 247)')
  }
  expect(theme.sampled.filter((item) => forbiddenDarkSurfaces.has(item.background))).toEqual([])
}

test.describe.configure({ mode: 'serial' })

test('四个目标视口使用暖白主题且没有页面级横向溢出', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => consoleErrors.push(error.message))

  const sizes = [
    { width: 390, height: 844, name: '390x844' },
    { width: 1366, height: 768, name: '1366x768' },
    { width: 1440, height: 900, name: '1440x900' },
    { width: 1920, height: 1080, name: '1920x1080' },
  ]

  for (const size of sizes) {
    await page.setViewportSize(size)
    await page.goto('/overview')
    await expect(page.getByRole('heading', { name: '经营总览' })).toBeVisible()
    await expect(page.locator('.kpi-card').first()).toBeVisible()
    await waitForDashboard(page)

    await expectWarmTheme(page, size.width)
    if (size.width >= 1366) {
      const ratio = await page.locator('.hourly-primary-grid').evaluate((grid) => {
        const main = grid.firstElementChild?.getBoundingClientRect().width ?? 0
        const aside = grid.lastElementChild?.getBoundingClientRect().width ?? 0
        return main / aside
      })
      expect(ratio).toBeGreaterThanOrEqual(1.8)
      expect(ratio).toBeLessThanOrEqual(2.2)
    }
    await expectNoPageOverflow(page)
    await expectNamedButtons(page)
    await page.screenshot({ path: artifactPath(size.name, 'overview.png'), fullPage: false })

    if (size.width === 390) {
      const filterToggle = page.getByRole('button', { name: /打开更多筛选/ })
      await expect(filterToggle).toBeVisible()
      await filterToggle.click()
      await expect(page.getByRole('dialog', { name: '更多筛选' })).toBeVisible()
      await expectNoPageOverflow(page)
      await page.getByRole('button', { name: '应用筛选' }).click()
      await expect(page.getByRole('dialog', { name: '更多筛选' })).toBeHidden()

      await page.getByRole('button', { name: '打开主导航' }).click()
      const mobileNavigation = page.getByRole('navigation', { name: '移动主导航' })
      await expect(mobileNavigation).toBeVisible()
      await expect(mobileNavigation.locator('.ant-menu-light')).toBeVisible()
      await expect(mobileNavigation.locator('.ant-menu-dark')).toHaveCount(0)
      await expect
        .poll(async () => Math.round((await mobileNavigation.boundingBox())?.x ?? -1))
        .toBeGreaterThanOrEqual(0)
      await expect
        .poll(async () => Math.round((await mobileNavigation.boundingBox())?.x ?? -1))
        .toBeLessThanOrEqual(12)
      await expect
        .poll(async () => Math.round((await mobileNavigation.boundingBox())?.width ?? -1))
        .toBeGreaterThan(250)
      await page.screenshot({
        path: artifactPath(size.name, 'mobile-navigation-open.png'),
        fullPage: false,
      })
      await page.keyboard.press('Escape')
      await expect(page.getByRole('navigation', { name: '移动主导航' })).toBeHidden()
    }
  }

  expect(consoleErrors).toEqual([])
})

test('经营总览保留周期、直播间、KPI、K线、目标线、详情与导出链路', async ({ page }) => {
  test.setTimeout(90_000)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/overview')
  await expect(page.locator('.kpi-card').first()).toBeVisible()
  await page.getByRole('radiogroup', { name: '快捷周期' }).getByText('7天').click()

  await page.getByLabel('直播间', { exact: true }).click()
  const firstRoom = page.locator('.ant-select-item-option').first()
  await expect(firstRoom).toBeVisible()
  await firstRoom.click()

  await page.getByRole('button', { name: /时段整体支付ROI/ }).click()
  await expect(page.getByText('当前聚焦：ROI')).toBeVisible()
  await expect(page.getByText(/ROI目标/).first()).toBeVisible()
  await expect(page.locator('.hourly-primary-grid canvas').first()).toBeVisible()

  await page.getByText('业务K线', { exact: true }).click()
  await expect(
    page.locator('.ant-segmented-item-selected').filter({ hasText: '业务K线' }),
  ).toBeVisible()
  await page.getByText('周期对比折线', { exact: true }).click()

  const details = page.getByRole('button', { name: /详情/ }).first()
  await expect(details).toBeVisible()
  await details.click()
  await expect(page.getByText(/分时详情/).first()).toBeVisible()
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: /更多设置与导出/ }).click()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: '导出数据' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/\.csv$/)
  await expectNoPageOverflow(page)
})

test('减少动态效果偏好同时关闭界面过渡与图表动画', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/overview')
  await expect(page.locator('.kpi-card').first()).toBeVisible()
  await expect(page.locator('.echarts-accessible-frame').first()).toHaveAttribute(
    'data-reduced-motion',
    'true',
  )
  const transitionDuration = await page
    .locator('.kpi-card')
    .first()
    .evaluate((card) =>
      getComputedStyle(card)
        .transitionDuration.split(',')
        .map((value) => Number.parseFloat(value) * (value.includes('ms') ? 1 : 1000)),
    )
  expect(Math.max(...transitionDuration)).toBeLessThanOrEqual(0.01)
})

test('主要分析、监控和管理页面统一暖白并输出最终截图', async ({ page }) => {
  test.setTimeout(120_000)
  const pages = [
    { route: '/overview', heading: '经营总览', file: 'overview-full.png' },
    { route: '/timeline', heading: '小时趋势', file: 'timeline.png' },
    { route: '/comparison', heading: '数据对比', file: 'comparison.png' },
    { route: '/anchors', heading: '主播分析', file: 'anchors.png' },
    { route: '/controls', heading: '场控分析', file: 'controls.png' },
    { route: '/pairings', heading: '主播 × 场控搭配', file: 'pairings.png' },
    { route: '/pivot', heading: '主播场控时间汇总透视表', file: 'pivot.png' },
    { route: '/alerts', heading: '主播趋势预警中心', file: 'alerts-rise.png' },
    { route: '/admin/sources', heading: '管理后台', file: 'admin-sources.png' },
    { route: '/admin/metrics', heading: '管理后台', file: 'admin-metrics.png' },
    { route: '/admin/shifts', heading: '管理后台', file: 'admin-shifts.png' },
    { route: '/admin/alert-rules', heading: '管理后台', file: 'admin-alert-rules.png' },
    { route: '/admin/settings', heading: '管理后台', file: 'admin-settings.png' },
    { route: '/admin/users', heading: '管理后台', file: 'admin-users.png' },
    { route: '/admin/audit-logs', heading: '管理后台', file: 'admin-audit-logs.png' },
  ]

  const screenshotViewports = [
    { width: 1440, height: 900, name: '1440x900' },
    { width: 1920, height: 1080, name: '1920x1080' },
  ]

  for (const viewport of screenshotViewports) {
    await page.setViewportSize(viewport)
    for (const item of pages) {
      await page.goto(item.route)
      await expect(page.getByRole('heading', { name: item.heading, level: 3 })).toBeVisible()
      await waitForDashboard(page)
      await expectWarmTheme(page, viewport.width)
      await expectNoPageOverflow(page)
      await expectNamedButtons(page)
      await page.screenshot({
        path: artifactPath(viewport.name, item.file),
        fullPage: true,
      })
    }
  }

  for (const viewport of screenshotViewports) {
    await page.setViewportSize(viewport)
    await page.goto('/alerts?tab=fall')
    await expect(page.getByRole('tab', { name: /下跌榜/ })).toHaveAttribute('aria-selected', 'true')
    await page.screenshot({
      path: artifactPath(viewport.name, 'alerts-fall.png'),
      fullPage: true,
    })
  }

  await page.goto('/pivot')
  await expect(page.getByRole('heading', { name: '主播场控时间汇总透视表' })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /CSV/ }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/\.csv$/)
})

test('记录隔离环境的前端业务就绪与资源数据', async ({ page }) => {
  await page.addInitScript(() => {
    const state = { lcp: 0, cls: 0, longTaskDuration: 0 }
    Object.defineProperty(window, '__dashboardPerformance', { value: state })
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) state.lcp = Math.max(state.lcp, entry.startTime)
    }).observe({ type: 'largest-contentful-paint', buffered: true })
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as Array<PerformanceEntry & { value?: number }>) {
        if (!(entry as PerformanceEntry & { hadRecentInput?: boolean }).hadRecentInput) {
          state.cls += entry.value ?? 0
        }
      }
    }).observe({ type: 'layout-shift', buffered: true })
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) state.longTaskDuration += entry.duration
    }).observe({ type: 'longtask', buffered: true })
  })

  const start = Date.now()
  await page.goto('/overview')
  await expect(page.locator('.kpi-card').first()).toBeVisible()
  const businessReadyMs = Date.now() - start
  await page.waitForTimeout(600)
  const metrics = await page.evaluate((ready) => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
    const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[]
    const state = (
      window as unknown as Window & {
        __dashboardPerformance: { lcp: number; cls: number; longTaskDuration: number }
      }
    ).__dashboardPerformance
    return {
      businessReadyMs: ready,
      domContentLoadedMs: navigation.domContentLoadedEventEnd,
      loadEventMs: navigation.loadEventEnd,
      resourceCount: resources.length,
      transferredBytes: resources.reduce((sum, item) => sum + item.transferSize, 0),
      lcpMs: state.lcp,
      cls: state.cls,
      longTaskDurationMs: state.longTaskDuration,
    }
  }, businessReadyMs)

  fs.mkdirSync(artifactRoot, { recursive: true })
  fs.writeFileSync(
    artifactPath('performance-e2e.json'),
    `${JSON.stringify(metrics, null, 2)}\n`,
    'utf8',
  )
  expect(metrics.businessReadyMs).toBeLessThan(10_000)
  expect(metrics.cls).toBeLessThanOrEqual(0.1)
})
