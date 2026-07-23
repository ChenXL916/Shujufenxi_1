import { chromium } from 'playwright'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const baseURL = process.env.UI_EVIDENCE_BASE_URL ?? 'http://127.0.0.1:5173'
const parsedBaseURL = new URL(baseURL)
const loopbackHosts = new Set(['127.0.0.1', '::1', 'localhost'])
if (
  !['http:', 'https:'].includes(parsedBaseURL.protocol) ||
  !loopbackHosts.has(parsedBaseURL.hostname)
) {
  throw new Error(`UI interaction verification only accepts loopback; received ${baseURL}`)
}

const evidenceRoot = path.resolve(process.cwd(), '../../docs/ui/evidence/after')
const statesDir = path.join(evidenceRoot, 'states')
const motionDir = path.join(evidenceRoot, 'motion')
await fs.mkdir(statesDir, { recursive: true })
await fs.mkdir(motionDir, { recursive: true })

const assertions = []
const failures = []
const blockedRequests = []
const failedRequests = []
const consoleErrors = []

function assert(name, condition, details = null) {
  assertions.push({ name, passed: Boolean(condition), details })
  if (!condition) failures.push({ name, details })
}

async function installSafetyGuard(page) {
  await page.route('**/*', async (route) => {
    const request = route.request()
    const requestUrl = new URL(request.url())
    const method = request.method().toUpperCase()
    const dangerousPath = /\/(scan|test|export|evaluate|recalculate|send|retry-push)(\/|$)/i.test(
      requestUrl.pathname,
    )
    const allowedProtocol = ['http:', 'https:', 'data:', 'blob:'].includes(requestUrl.protocol)
    const localNetwork =
      ['data:', 'blob:'].includes(requestUrl.protocol) || loopbackHosts.has(requestUrl.hostname)
    const readOnly = ['GET', 'HEAD', 'OPTIONS'].includes(method)
    if (!allowedProtocol || !localNetwork || !readOnly || dangerousPath) {
      blockedRequests.push(`${method} ${requestUrl.origin}${requestUrl.pathname}`)
      await route.abort('blockedbyclient')
      return
    }
    await route.continue()
  })
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => consoleErrors.push(error.message))
  page.on('requestfailed', (request) => {
    const errorText = request.failure()?.errorText ?? 'failed'
    if (errorText === 'net::ERR_ABORTED') return
    failedRequests.push(`${request.method()} ${request.url()} :: ${errorText}`)
  })
}

async function openPage(page, route) {
  await page.goto(`${baseURL}${route}`, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.locator('.app-shell').waitFor({ state: 'visible', timeout: 15_000 })
  await page.locator('.page-heading h3').first().waitFor({ state: 'visible', timeout: 15_000 })
  await page.evaluate(() => document.fonts.ready)
  await page
    .locator('.ant-skeleton')
    .first()
    .waitFor({ state: 'hidden', timeout: 8_000 })
    .catch(() => {})
}

async function documentHasNoOverflow(page) {
  return page.evaluate(
    () =>
      document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1 &&
      document.body.scrollWidth <= window.innerWidth + 1,
  )
}

async function waitForFocus(page, locator) {
  const handle = await locator.elementHandle()
  if (!handle) return { focused: false, details: { target: 'missing' } }
  let focused = true
  try {
    await page.waitForFunction((element) => document.activeElement === element, handle, {
      timeout: 2_000,
    })
  } catch {
    focused = false
  }
  const details = await page.evaluate((element) => {
    const target = element
    const active = document.activeElement
    const rect = target.getBoundingClientRect()
    return {
      activeTag: active?.tagName ?? null,
      activeClass: active?.getAttribute('class') ?? null,
      activeLabel:
        active?.getAttribute('aria-label') ?? active?.textContent?.trim().slice(0, 80) ?? null,
      targetConnected: target.isConnected,
      targetDisabled: target.matches(':disabled'),
      targetTabIndex: target.tabIndex,
      targetVisible: rect.width > 0 && rect.height > 0,
    }
  }, handle)
  await handle.dispose()
  return { focused, details }
}

async function waitForOverlaySettled(page, locator) {
  const handle = await locator.elementHandle()
  if (!handle) return
  try {
    await page.waitForFunction(
      (element) => {
        const rect = element.getBoundingClientRect()
        return rect.left >= -1 && rect.right <= window.innerWidth + 1
      },
      handle,
      { timeout: 2_000 },
    )
  } finally {
    await handle.dispose()
  }
}

async function renameVideo(video, targetName) {
  if (!video) return null
  const source = await video.path()
  const target = path.join(motionDir, targetName)
  await fs.rm(target, { force: true })
  await fs.rename(source, target)
  return path.relative(path.resolve(process.cwd(), '../..'), target).replaceAll('\\', '/')
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const browserVersion = browser.version()
let mobileVideo = null
let desktopVideo = null
try {
  const mobileContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    deviceScaleFactor: 1,
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    recordVideo: { dir: motionDir, size: { width: 390, height: 844 } },
  })
  const mobilePage = await mobileContext.newPage()
  mobileVideo = mobilePage.video()
  await installSafetyGuard(mobilePage)

  await openPage(mobilePage, '/overview')
  assert('390经营总览无页面级横向溢出', await documentHasNoOverflow(mobilePage))

  const navigationTrigger = mobilePage.getByRole('button', { name: '打开主导航' })
  await navigationTrigger.focus()
  await navigationTrigger.click()
  const navigationDialog = mobilePage.getByRole('dialog', { name: '直播运营驾驶舱' })
  await navigationDialog.waitFor({ state: 'visible' })
  await waitForOverlaySettled(mobilePage, navigationDialog)
  assert(
    '移动导航保留同步入口',
    await navigationDialog.getByRole('button', { name: /立即同步|授权飞书/ }).isVisible(),
  )
  await mobilePage.screenshot({ path: path.join(statesDir, 'mobile-navigation.png') })
  await mobilePage.keyboard.press('Escape')
  await navigationDialog.waitFor({ state: 'hidden' })
  const navigationFocus = await waitForFocus(mobilePage, navigationTrigger)
  assert('移动导航关闭后焦点返回触发按钮', navigationFocus.focused, navigationFocus.details)

  const filterTrigger = mobilePage.getByRole('button', { name: /更多筛选/ })
  await filterTrigger.focus()
  await filterTrigger.click()
  const filterDialog = mobilePage.getByRole('dialog', { name: '更多筛选' })
  await filterDialog.waitFor({ state: 'visible' })
  await waitForOverlaySettled(mobilePage, filterDialog)
  const filterBounds = await filterDialog.boundingBox()
  assert(
    '移动筛选Drawer限制在视口内',
    Boolean(
      filterBounds &&
      filterBounds.x >= -1 &&
      filterBounds.x + filterBounds.width <= 391 &&
      filterBounds.width <= 391,
    ),
    filterBounds,
  )
  const drawerActionSizes = await filterDialog
    .getByRole('button', { name: /重\s*置|应\s*用/ })
    .evaluateAll((elements) =>
      elements.map((element) => {
        const rect = element.getBoundingClientRect()
        return { text: element.textContent?.trim(), width: rect.width, height: rect.height }
      }),
    )
  assert(
    '移动筛选Drawer操作区命中尺寸至少44px',
    drawerActionSizes.length === 2 && drawerActionSizes.every((item) => item.height >= 44),
    drawerActionSizes,
  )
  await mobilePage.screenshot({ path: path.join(statesDir, 'mobile-filter-drawer.png') })
  await mobilePage.keyboard.press('Escape')
  await filterDialog.waitFor({ state: 'hidden' })
  const filterFocus = await waitForFocus(mobilePage, filterTrigger)
  assert('移动筛选Drawer关闭后焦点返回触发按钮', filterFocus.focused, filterFocus.details)

  const dateClearSizes = await mobilePage.locator('.ant-picker-clear').evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect()
      return { width: rect.width, height: rect.height }
    }),
  )
  assert(
    '移动日期清除按钮命中尺寸至少44px',
    dateClearSizes.length > 0 &&
      dateClearSizes.every((item) => item.width >= 44 && item.height >= 44),
    dateClearSizes,
  )
  const kpiLayout = await mobilePage.locator('.kpi-grid').evaluate((grid) => ({
    columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
    values: Array.from(grid.querySelectorAll('.kpi-value')).map((element) => ({
      text: element.textContent?.trim(),
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      ariaLabel: element.getAttribute('aria-label'),
    })),
  }))
  assert('390 KPI使用单列布局', kpiLayout.columns === 1, kpiLayout)
  assert(
    '390 KPI数值完整且有完整值语义',
    kpiLayout.values.length > 0 &&
      kpiLayout.values.every(
        (item) => item.text && item.ariaLabel && item.scrollWidth <= item.clientWidth + 1,
      ),
    kpiLayout.values,
  )
  const chartFrameLocator = mobilePage.locator('[data-chart-resize-observer="true"]')
  await chartFrameLocator
    .first()
    .waitFor({ state: 'visible', timeout: 10_000 })
    .catch(() => {})
  const chartFrames = await chartFrameLocator.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect()
      return { left: rect.left, right: rect.right, width: rect.width }
    }),
  )
  assert(
    '390图表容器均在视口内',
    chartFrames.length > 0 && chartFrames.every((item) => item.left >= 0 && item.right <= 391),
    chartFrames,
  )

  await openPage(mobilePage, '/timeline')
  const pointSelect = mobilePage.getByRole('combobox', { name: /选择数据点打开详情/ }).first()
  await pointSelect.focus()
  await pointSelect.click()
  const firstPoint = mobilePage
    .locator('.ant-select-item-option:not(.ant-select-item-option-disabled)')
    .first()
  await firstPoint.waitFor({ state: 'visible' })
  await firstPoint.click()
  const openDetailButton = mobilePage.getByRole('button', { name: /打开所选数据点详情/ }).first()
  await openDetailButton.waitFor({ state: 'visible' })
  assert('Timeline选择数据点后详情按钮可用', await openDetailButton.isEnabled())
  await openDetailButton.focus()
  await mobilePage.keyboard.press('Enter')
  const detailDialog = mobilePage.getByRole('dialog', { name: '数据点详情' })
  await detailDialog.waitFor({ state: 'visible' })
  await waitForOverlaySettled(mobilePage, detailDialog)
  const detailBounds = await detailDialog.boundingBox()
  assert(
    'Timeline详情Drawer限制在移动视口内',
    Boolean(
      detailBounds &&
      detailBounds.x >= -1 &&
      detailBounds.x + detailBounds.width <= 391 &&
      detailBounds.width <= 391,
    ),
    detailBounds,
  )
  const detailLayout = await detailDialog.evaluate((element) => ({
    headings: Array.from(element.querySelectorAll('h3, h4, h5')).map((heading) =>
      heading.textContent?.trim(),
    ),
    rawText: element.textContent ?? '',
    metricGrids: Array.from(element.querySelectorAll('.detail-metric-grid')).map((grid) => ({
      columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
      clientWidth: grid.clientWidth,
      scrollWidth: grid.scrollWidth,
    })),
    metricValues: Array.from(element.querySelectorAll('.detail-metric-value')).map((value) => ({
      text: value.textContent?.trim(),
      clientWidth: value.clientWidth,
      scrollWidth: value.scrollWidth,
    })),
  }))
  assert(
    'Timeline详情使用中文信息层级和指标分组',
    detailLayout.headings.includes('标准化指标') &&
      detailLayout.headings.includes('本时段表现') &&
      !detailLayout.rawText.includes('hour_slot') &&
      !detailLayout.rawText.includes('anchor_match_status'),
    detailLayout,
  )
  assert(
    'Timeline详情390px指标为单列且数值不截断',
    detailLayout.metricGrids.length > 0 &&
      detailLayout.metricGrids.every(
        (grid) => grid.columns === 1 && grid.scrollWidth <= grid.clientWidth + 1,
      ) &&
      detailLayout.metricValues.length > 0 &&
      detailLayout.metricValues.every((value) => value.scrollWidth <= value.clientWidth + 1),
    detailLayout,
  )
  await mobilePage.screenshot({ path: path.join(statesDir, 'timeline-detail-drawer.png') })
  await detailDialog.locator('.ant-drawer-close').focus()
  await mobilePage.keyboard.press('Escape')
  await detailDialog.waitFor({ state: 'hidden' })
  const detailFocus = await waitForFocus(mobilePage, openDetailButton)
  assert('Timeline详情关闭后焦点返回打开详情按钮', detailFocus.focused, detailFocus.details)

  await openPage(mobilePage, '/comparison')
  const comparisonTable = await mobilePage
    .locator('.ant-table-content')
    .first()
    .evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }))
  assert(
    'Comparison宽表使用局部横向滚动',
    comparisonTable.scrollWidth > comparisonTable.clientWidth,
    comparisonTable,
  )
  assert('Comparison仍无页面级横向溢出', await documentHasNoOverflow(mobilePage))

  await mobileContext.close()

  const desktopContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    deviceScaleFactor: 1,
    colorScheme: 'light',
    reducedMotion: 'no-preference',
    recordVideo: { dir: motionDir, size: { width: 1440, height: 900 } },
  })
  const desktopPage = await desktopContext.newPage()
  desktopVideo = desktopPage.video()
  await installSafetyGuard(desktopPage)
  await openPage(desktopPage, '/overview')
  const firstChart = desktopPage.locator('[data-chart-resize-observer="true"]').first()
  const chartBefore = await firstChart.evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    canvases: element.querySelectorAll('canvas').length,
  }))
  const collapseButton = desktopPage.getByRole('button', { name: '折叠主导航' })
  const siderDuration = await desktopPage.locator('.app-sider').evaluate((element) =>
    getComputedStyle(element)
      .transitionDuration.split(',')
      .map((value) =>
        value.endsWith('ms') ? Number.parseFloat(value) / 1000 : Number.parseFloat(value),
      ),
  )
  assert(
    '侧栏Motion不超过300ms',
    siderDuration.length > 0 && siderDuration.every((value) => value <= 0.3),
    siderDuration,
  )
  await collapseButton.click()
  await desktopPage.getByRole('button', { name: '展开主导航' }).waitFor({ state: 'visible' })
  await desktopPage.waitForTimeout(320)
  const chartAfter = await firstChart.evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    canvases: element.querySelectorAll('canvas').length,
  }))
  assert('侧栏折叠后图表容器获得空间', chartAfter.width > chartBefore.width, {
    before: chartBefore,
    after: chartAfter,
  })
  assert(
    '侧栏折叠后ECharts未重复初始化',
    chartBefore.canvases === chartAfter.canvases && chartAfter.canvases === 1,
    { before: chartBefore, after: chartAfter },
  )
  const collapsedMenuLabels = await desktopPage.locator('.app-sider').evaluate((sider) => ({
    groups: Array.from(sider.querySelectorAll('.ant-menu-item-group-title')).map((element) => {
      const rect = element.getBoundingClientRect()
      return {
        text: element.textContent?.trim(),
        display: getComputedStyle(element).display,
        width: rect.width,
        height: rect.height,
      }
    }),
    items: Array.from(sider.querySelectorAll('.ant-menu-title-content')).map((element) => {
      const rect = element.getBoundingClientRect()
      return {
        text: element.textContent?.trim(),
        opacity: getComputedStyle(element).opacity,
        width: rect.width,
      }
    }),
  }))
  assert(
    '侧栏折叠后分组与菜单文字不残留裁切片段',
    collapsedMenuLabels.groups.length > 0 &&
      collapsedMenuLabels.groups.every(
        (item) => item.display === 'none' && item.width === 0 && item.height === 0,
      ) &&
      collapsedMenuLabels.items.length > 0 &&
      collapsedMenuLabels.items.every((item) => item.opacity === '0' && item.width === 0),
    collapsedMenuLabels,
  )
  await desktopPage.screenshot({ path: path.join(statesDir, 'desktop-sidebar-collapsed.png') })

  const dimensionSelect = desktopPage.locator('.hourly-dimension-select')
  await dimensionSelect.scrollIntoViewIfNeeded()
  await dimensionSelect.getByRole('combobox', { name: '24小时图表拆分方式' }).click()
  const dimensionPopup = desktopPage.locator(
    '.ant-select-dropdown:not(.ant-select-dropdown-hidden)',
  )
  await dimensionPopup.waitFor({ state: 'visible' })
  const dimensionGeometry = {
    trigger: await dimensionSelect.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { width: rect.width, left: rect.left, right: rect.right }
    }),
    popup: await dimensionPopup.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { width: rect.width, left: rect.left, right: rect.right }
    }),
    options: await dimensionPopup
      .locator('.ant-select-item-option-content')
      .evaluateAll((elements) =>
        elements.map((element) => ({
          text: element.textContent?.trim(),
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
        })),
      ),
  }
  assert(
    '拆分下拉触发器和全部选项文字完整可读',
    dimensionGeometry.trigger.width >= 112 &&
      dimensionGeometry.popup.width >= 144 &&
      dimensionGeometry.options.length === 4 &&
      dimensionGeometry.options.every((item) => item.scrollWidth <= item.clientWidth + 1),
    dimensionGeometry,
  )
  await desktopPage.screenshot({
    path: path.join(statesDir, 'desktop-hourly-dimension-select.png'),
  })
  await desktopPage.keyboard.press('Escape')
  await dimensionPopup.waitFor({ state: 'hidden' })
  assert('1440经营总览无页面级横向溢出', await documentHasNoOverflow(desktopPage))
  await desktopContext.close()

  const reducedContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    reducedMotion: 'reduce',
  })
  const reducedPage = await reducedContext.newPage()
  await installSafetyGuard(reducedPage)
  await openPage(reducedPage, '/overview')
  const reducedDurations = await reducedPage.locator('.app-sider').evaluate((element) =>
    getComputedStyle(element)
      .transitionDuration.split(',')
      .map((value) =>
        value.endsWith('ms') ? Number.parseFloat(value) / 1000 : Number.parseFloat(value),
      ),
  )
  assert(
    'Reduce Motion将侧栏过渡缩短到近零',
    reducedDurations.every((value) => value <= 0.01),
    reducedDurations,
  )
  await reducedContext.close()
} finally {
  await browser.close()
}

const videos = {
  mobileDrawers: await renameVideo(mobileVideo, 'mobile-drawers.webm').catch((error) => {
    failures.push({ name: '移动动画录屏生成', details: String(error) })
    return null
  }),
  sidebarCollapse: await renameVideo(desktopVideo, 'sidebar-collapse.webm').catch((error) => {
    failures.push({ name: '侧栏动画录屏生成', details: String(error) })
    return null
  }),
}

if (blockedRequests.length)
  failures.push({ name: '浏览器验收触发了被阻断请求', details: blockedRequests })
if (failedRequests.length)
  failures.push({ name: '浏览器验收存在失败请求', details: failedRequests })
if (consoleErrors.length)
  failures.push({ name: '浏览器验收存在Console错误', details: consoleErrors })

const report = {
  baseURL,
  capturedAt: new Date().toISOString(),
  browserVersion,
  assertions,
  failures,
  blockedRequests,
  failedRequests,
  consoleErrors,
  videos,
  passed: failures.length === 0,
}
await fs.writeFile(
  path.join(evidenceRoot, 'interactions.json'),
  `${JSON.stringify(report, null, 2)}\n`,
)
console.log(JSON.stringify(report, null, 2))
if (!report.passed) process.exitCode = 1
