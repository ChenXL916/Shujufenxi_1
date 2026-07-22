import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const target = process.env.PERFORMANCE_URL ?? 'http://127.0.0.1:4174/overview'
const output = path.resolve(
  process.env.PERFORMANCE_OUTPUT ??
    '../../artifacts/index-redesign/after/performance-production.json',
)
const thresholds = {
  businessReadyMs: 5_000,
  lcpMs: 2_500,
  cls: 0.1,
  blockingTimeMs: 200,
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right)
  return sorted[Math.floor(sorted.length / 2)]
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const runs = []

try {
  for (let index = 0; index < 3; index += 1) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await context.newPage()
    const runtimeErrors = []
    page.on('console', (message) => {
      if (message.type() === 'error') runtimeErrors.push(message.text())
    })
    page.on('pageerror', (error) => runtimeErrors.push(error.message))
    await page.addInitScript(() => {
      const state = { lcp: 0, cls: 0, longTasks: [] }
      Object.defineProperty(window, '__productionPerformance', { value: state })
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) state.lcp = Math.max(state.lcp, entry.startTime)
      }).observe({ type: 'largest-contentful-paint', buffered: true })
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) state.cls += entry.value ?? 0
        }
      }).observe({ type: 'layout-shift', buffered: true })
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) state.longTasks.push(entry.duration)
      }).observe({ type: 'longtask', buffered: true })
    })

    const startedAt = Date.now()
    await page.goto(target, { waitUntil: 'domcontentloaded' })
    await page.locator('.kpi-card').first().waitFor({ state: 'visible', timeout: 10_000 })
    const businessReadyMs = Date.now() - startedAt
    await page.waitForTimeout(1_200)
    const result = await page.evaluate((ready) => {
      const navigation = performance.getEntriesByType('navigation')[0]
      const resources = performance.getEntriesByType('resource')
      const paint = performance.getEntriesByName('first-contentful-paint')[0]
      const state = window.__productionPerformance
      return {
        businessReadyMs: ready,
        domContentLoadedMs: navigation.domContentLoadedEventEnd,
        loadEventMs: navigation.loadEventEnd,
        fcpMs: paint?.startTime ?? 0,
        lcpMs: state.lcp,
        cls: state.cls,
        blockingTimeMs: state.longTasks.reduce(
          (total, duration) => total + Math.max(0, duration - 50),
          0,
        ),
        longestTaskMs: Math.max(0, ...state.longTasks),
        resourceCount: resources.length,
        transferredBytes: resources.reduce((total, entry) => total + (entry.transferSize ?? 0), 0),
      }
    }, businessReadyMs)
    runs.push({ run: index + 1, ...result, runtimeErrors })
    await context.close()
  }
} finally {
  await browser.close()
}

const metricNames = [
  'businessReadyMs',
  'domContentLoadedMs',
  'loadEventMs',
  'fcpMs',
  'lcpMs',
  'cls',
  'blockingTimeMs',
  'longestTaskMs',
  'resourceCount',
  'transferredBytes',
]
const medians = Object.fromEntries(
  metricNames.map((name) => [name, median(runs.map((run) => run[name]))]),
)
const passed =
  runs.every((run) => run.runtimeErrors.length === 0) &&
  medians.businessReadyMs <= thresholds.businessReadyMs &&
  medians.lcpMs <= thresholds.lcpMs &&
  medians.cls <= thresholds.cls &&
  medians.blockingTimeMs <= thresholds.blockingTimeMs
const report = { target, sampledAt: new Date().toISOString(), thresholds, passed, medians, runs }
fs.mkdirSync(path.dirname(output), { recursive: true })
fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(report, null, 2))
if (!passed) process.exitCode = 1
