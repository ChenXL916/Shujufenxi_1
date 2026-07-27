import { chromium } from '@playwright/test'

const entryUrl = process.argv[2] ?? 'https://chenxl916.github.io/Shujufenxi_1/'
const browser = await chromium.launch({ headless: true })

try {
  const page = await browser.newPage()
  await page.goto(entryUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.waitForURL(
    (url) => url.protocol === 'https:' && url.hostname.toLowerCase().endsWith('.trycloudflare.com'),
    { timeout: 30_000 },
  )
  await page.getByRole('button', { name: '登录并查看数据' }).waitFor({
    state: 'visible',
    timeout: 30_000,
  })

  const endpoints = await page.evaluate(async () => {
    const inspect = async (path) => {
      const response = await fetch(path, { cache: 'no-store' })
      return {
        path,
        status: response.status,
        contentType: response.headers.get('content-type'),
      }
    }
    return Promise.all([inspect('/health'), inspect('/ready'), inspect('/auth/me')])
  })

  const expected = new Map([
    ['/health', 200],
    ['/ready', 200],
    ['/auth/me', 401],
  ])
  for (const endpoint of endpoints) {
    if (endpoint.status !== expected.get(endpoint.path)) {
      throw new Error(
        `${endpoint.path} returned ${endpoint.status}; expected ${expected.get(endpoint.path)}`,
      )
    }
  }

  console.log(
    JSON.stringify(
      {
        entryUrl,
        destinationUrl: page.url(),
        loginVisible: true,
        endpoints,
      },
      null,
      2,
    ),
  )
} finally {
  await browser.close()
}
