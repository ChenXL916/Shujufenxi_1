import { chromium } from 'playwright'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const phase = process.argv[2] ?? 'before'
if (!['before', 'after'].includes(phase)) {
  throw new Error('Usage: node scripts/capture-ui-evidence.mjs before|after')
}

const baseURL = process.env.UI_EVIDENCE_BASE_URL ?? 'http://127.0.0.1:5173'
const parsedBaseURL = new URL(baseURL)
const loopbackHosts = new Set(['127.0.0.1', '::1', 'localhost'])
if (
  !['http:', 'https:'].includes(parsedBaseURL.protocol) ||
  !loopbackHosts.has(parsedBaseURL.hostname)
) {
  throw new Error(`UI evidence capture only accepts a loopback base URL; received ${baseURL}`)
}
const outputRoot = path.resolve(process.cwd(), `../../docs/ui/evidence/${phase}`)
const viewports = [
  { name: '390x844', width: 390, height: 844 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '1024x768', width: 1024, height: 768 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1920x1080', width: 1920, height: 1080 },
]
const pages = [
  { key: 'overview', route: '/overview' },
  { key: 'timeline', route: '/timeline' },
  { key: 'comparison', route: '/comparison' },
  { key: 'anchors', route: '/anchors' },
  { key: 'controls', route: '/controls' },
  { key: 'pairings', route: '/pairings' },
  { key: 'pivot', route: '/pivot' },
  { key: 'alerts-rise', route: '/alerts?tab=rise' },
  { key: 'alerts-fall', route: '/alerts?tab=fall' },
  { key: 'admin-sources', route: '/admin/sources' },
  { key: 'admin-metrics', route: '/admin/metrics' },
  { key: 'admin-shifts', route: '/admin/shifts' },
  { key: 'admin-alert-rules', route: '/admin/alert-rules' },
  { key: 'admin-users', route: '/admin/users' },
  { key: 'admin-settings', route: '/admin/settings' },
  { key: 'admin-audit-logs', route: '/admin/audit-logs' },
]

function filterEvidenceItems(items, environmentName) {
  const requested = process.env[environmentName]
    ?.split(',')
    .map((value) => value.trim())
    .filter(Boolean)
  if (!requested?.length) return items
  const requestedSet = new Set(requested)
  const selected = items.filter((item) => requestedSet.has(item.name ?? item.key))
  if (!selected.length) throw new Error(`${environmentName} did not match any configured item`)
  return selected
}

const captureViewports = filterEvidenceItems(viewports, 'UI_EVIDENCE_VIEWPORTS')
const capturePages = filterEvidenceItems(pages, 'UI_EVIDENCE_PAGES')

if (phase === 'before' && process.env.UI_EVIDENCE_ALLOW_OVERWRITE !== '1') {
  const existingBaseline = await fs
    .access(path.join(outputRoot, 'metrics.json'))
    .then(() => true)
    .catch(() => false)
  if (existingBaseline) {
    throw new Error('Refusing to overwrite the existing before baseline')
  }
}
await fs.mkdir(outputRoot, { recursive: true })
const sourceFiles = [
  'src/App.tsx',
  'src/styles/global.css',
  'src/theme/dashboardTheme.ts',
  'src/theme/chartTheme.ts',
  'src/components/ECharts.tsx',
  'src/components/FilterBar.tsx',
  'src/components/KpiCard.tsx',
  'package-lock.json',
]
const sourceHashes = Object.fromEntries(
  await Promise.all(
    sourceFiles.map(async (file) => {
      const content = await fs.readFile(path.resolve(process.cwd(), file))
      return [file, crypto.createHash('sha256').update(content).digest('hex')]
    }),
  ),
)
const results = []
let browserVersion = null

for (const viewport of captureViewports) {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  browserVersion ??= browser.version()
  try {
    const context = await browser.newContext({
      viewport,
      locale: 'zh-CN',
      timezoneId: 'Asia/Shanghai',
      deviceScaleFactor: 1,
      colorScheme: 'light',
      reducedMotion: 'reduce',
    })
    const page = await context.newPage()
    for (const item of capturePages) {
      const consoleErrors = []
      const failedRequests = []
      const blockedRequests = []
      const routeGuard = async (route) => {
        const request = route.request()
        const requestUrl = new URL(request.url())
        const method = request.method().toUpperCase()
        const dangerousPath =
          /\/(scan|test|export|evaluate|recalculate|send|retry-push)(\/|$)/i.test(
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
      }
      await page.route('**/*', routeGuard)
      const onConsole = (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      }
      const onPageError = (error) => consoleErrors.push(error.message)
      const onRequestFailed = (request) => {
        failedRequests.push(
          `${request.method()} ${request.url()} :: ${request.failure()?.errorText ?? 'failed'}`,
        )
      }
      page.on('console', onConsole)
      page.on('pageerror', onPageError)
      page.on('requestfailed', onRequestFailed)

      const startedAt = Date.now()
      let navigationError = null
      try {
        await page.goto(`${baseURL}${item.route}`, {
          waitUntil: 'domcontentloaded',
          timeout: 30_000,
        })
        await page.locator('.app-shell').waitFor({ state: 'visible', timeout: 15_000 })
        await page
          .locator('.page-heading h3')
          .first()
          .waitFor({ state: 'visible', timeout: 15_000 })
        await page.evaluate(() => document.fonts.ready)
        await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {})
        await page
          .locator('.ant-skeleton')
          .first()
          .waitFor({ state: 'hidden', timeout: 8_000 })
          .catch(() => {})
      } catch (error) {
        navigationError = error instanceof Error ? error.message : String(error)
      }

      const metrics = await page
        .evaluate(() => {
          const visible = (element) => {
            const rect = element.getBoundingClientRect()
            const style = getComputedStyle(element)
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== 'hidden' &&
              style.display !== 'none'
            )
          }
          const descriptor = (element) => ({
            tag: element.tagName.toLowerCase(),
            className: typeof element.className === 'string' ? element.className.slice(0, 180) : '',
            text: (element.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 160),
          })
          const clippingSelectors = [
            '.page-heading h3',
            '.page-description',
            '.ant-card-head-title',
            '.ant-table-thead th',
            '.ant-btn',
            '.ant-tag',
            '.kpi-label',
            '.kpi-value',
            '.ant-select-selection-item',
          ].join(',')
          const clippedText = Array.from(document.querySelectorAll(clippingSelectors))
            .filter((element) => visible(element))
            .map((element) => {
              const html = element
              const tableTitle = html.matches('.ant-table-thead th')
                ? html.querySelector('.ant-table-column-title')
                : null
              const measurement = tableTitle ?? html
              const style = getComputedStyle(measurement)
              const range = document.createRange()
              range.selectNodeContents(measurement)
              const textWidth = Math.ceil(
                Math.max(0, ...Array.from(range.getClientRects()).map((rect) => rect.width)),
              )
              return {
                ...descriptor(html),
                clientWidth: Math.round(measurement.clientWidth),
                scrollWidth: Math.round(measurement.scrollWidth),
                textWidth,
                clientHeight: Math.round(measurement.clientHeight),
                scrollHeight: Math.round(measurement.scrollHeight),
                overflow: style.overflow,
                textOverflow: style.textOverflow,
                whiteSpace: style.whiteSpace,
                title: html.getAttribute('title'),
                ariaLabel: html.getAttribute('aria-label'),
              }
            })
            .filter(
              (item) =>
                item.textWidth > item.clientWidth + 2 || item.scrollHeight > item.clientHeight + 3,
            )
            .slice(0, 100)

          const iconMetrics = Array.from(document.querySelectorAll('.anticon'))
            .filter((element) => visible(element))
            .map((element) => {
              const rect = element.getBoundingClientRect()
              const parent = element.closest('button, a, .ant-menu-item, .ant-tag, .status-badge')
              const parentRect = parent?.getBoundingClientRect()
              return {
                ...descriptor(element),
                width: Number(rect.width.toFixed(2)),
                height: Number(rect.height.toFixed(2)),
                parentTag: parent?.tagName.toLowerCase() ?? null,
                parentText: (parent?.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 80),
                centerOffsetY: parentRect
                  ? Number(
                      (
                        rect.top +
                        rect.height / 2 -
                        (parentRect.top + parentRect.height / 2)
                      ).toFixed(2),
                    )
                  : null,
              }
            })

          const buttons = Array.from(
            document.querySelectorAll('button, a[role="button"], .header-icon-link'),
          )
            .filter((element) => visible(element))
            .map((element) => {
              const rect = element.getBoundingClientRect()
              const text = (element.textContent ?? '').replace(/\s+/g, ' ').trim()
              const hasIcon = element.querySelector('.anticon') !== null
              return {
                ...descriptor(element),
                width: Number(rect.width.toFixed(2)),
                height: Number(rect.height.toFixed(2)),
                hasIcon,
                iconOnly: hasIcon && text.length === 0,
                accessibleName:
                  element.getAttribute('aria-label') ||
                  element.getAttribute('title') ||
                  text ||
                  null,
              }
            })

          const tables = Array.from(document.querySelectorAll('.ant-table-wrapper')).map(
            (element) => ({
              ...descriptor(element),
              clientWidth: Math.round(element.clientWidth),
              scrollWidth: Math.round(element.scrollWidth),
              contentScrollWidth: Math.round(
                element.querySelector('.ant-table-content')?.scrollWidth ?? element.scrollWidth,
              ),
            }),
          )

          return {
            url: window.location.href,
            heading: document.querySelector('.page-heading h3')?.textContent?.trim() ?? null,
            document: {
              clientWidth: document.documentElement.clientWidth,
              scrollWidth: document.documentElement.scrollWidth,
              bodyScrollWidth: document.body.scrollWidth,
              viewportWidth: window.innerWidth,
              pageOverflow:
                document.documentElement.scrollWidth !== document.documentElement.clientWidth ||
                document.body.scrollWidth > window.innerWidth,
            },
            clippedText,
            iconMetrics,
            iconSizes: Array.from(
              new Set(iconMetrics.map((item) => `${item.width}x${item.height}`)),
            ).sort(),
            misalignedIcons: iconMetrics.filter(
              (item) => item.centerOffsetY !== null && Math.abs(item.centerOffsetY) > 1.5,
            ),
            unnamedIconButtons: buttons.filter((item) => item.iconOnly && !item.accessibleName),
            undersizedMobileTargets: buttons.filter(
              (item) =>
                window.innerWidth <= 768 && item.iconOnly && (item.width < 44 || item.height < 44),
            ),
            tables,
          }
        })
        .catch((error) => ({
          evaluationError: error instanceof Error ? error.message : String(error),
        }))

      const viewportDir = path.join(outputRoot, viewport.name)
      await fs.mkdir(viewportDir, { recursive: true })
      const screenshotPath = path.join(viewportDir, `${item.key}.png`)
      try {
        await page.screenshot({ path: screenshotPath, fullPage: true, animations: 'disabled' })
      } catch (error) {
        navigationError ??= `screenshot: ${error instanceof Error ? error.message : String(error)}`
      }

      const result = {
        phase,
        viewport,
        page: item,
        durationMs: Date.now() - startedAt,
        navigationError,
        consoleErrors,
        failedRequests,
        blockedRequests,
        screenshot: path
          .relative(path.resolve(process.cwd(), '../..'), screenshotPath)
          .replaceAll('\\', '/'),
        metrics,
      }
      results.push(result)
      await fs.writeFile(
        path.join(outputRoot, 'metrics.partial.json'),
        `${JSON.stringify({ phase, baseURL, results }, null, 2)}\n`,
      )
      page.off('console', onConsole)
      page.off('pageerror', onPageError)
      page.off('requestfailed', onRequestFailed)
      await page.unroute('**/*', routeGuard)
      console.log(`${phase} ${viewport.name} ${item.key} ${navigationError ? 'ERROR' : 'OK'}`)
      await page.goto('about:blank').catch(() => {})
    }
    await context.close()
  } finally {
    await browser.close()
  }
}

const summary = {
  phase,
  baseURL,
  capturedAt: new Date().toISOString(),
  browserVersion,
  nodeVersion: process.version,
  sourceHashes,
  viewports: captureViewports.length,
  pages: capturePages.length,
  screenshots: results.length,
  navigationErrors: results.filter((item) => item.navigationError).length,
  pageOverflow: results.filter((item) => item.metrics?.document?.pageOverflow).length,
  clippedText: results.reduce((sum, item) => sum + (item.metrics?.clippedText?.length ?? 0), 0),
  misalignedIcons: results.reduce(
    (sum, item) => sum + (item.metrics?.misalignedIcons?.length ?? 0),
    0,
  ),
  unnamedIconButtons: results.reduce(
    (sum, item) => sum + (item.metrics?.unnamedIconButtons?.length ?? 0),
    0,
  ),
  undersizedMobileTargets: results.reduce(
    (sum, item) => sum + (item.metrics?.undersizedMobileTargets?.length ?? 0),
    0,
  ),
  consoleErrors: results.reduce((sum, item) => sum + item.consoleErrors.length, 0),
  failedRequests: results.reduce((sum, item) => sum + item.failedRequests.length, 0),
  blockedRequests: results.reduce((sum, item) => sum + item.blockedRequests.length, 0),
}
await fs.writeFile(
  path.join(outputRoot, 'metrics.json'),
  `${JSON.stringify({ summary, results }, null, 2)}\n`,
)
console.log(JSON.stringify(summary, null, 2))
const gateFailures =
  summary.navigationErrors +
  summary.pageOverflow +
  summary.unnamedIconButtons +
  summary.undersizedMobileTargets +
  summary.consoleErrors +
  summary.failedRequests +
  summary.blockedRequests
if (phase === 'after' && gateFailures > 0) process.exitCode = 1
else if (summary.navigationErrors > 0) process.exitCode = 1
