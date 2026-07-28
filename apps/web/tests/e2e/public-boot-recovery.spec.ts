import { expect, test } from '@playwright/test'

test('shows a loading shell while the entry chunk is still downloading', async ({ page }) => {
  await page.route('**/src/main.tsx', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500))
    await route.continue()
  })

  const navigation = page.goto('/login')
  await expect(page.getByRole('heading', { name: '正在加载仪表盘' })).toBeVisible()
  await navigation
  await expect(page.locator('#root > *')).toBeVisible()
  await expect(page.getByRole('heading', { name: '正在加载仪表盘' })).toHaveCount(0)
})

test('shows a recoverable page instead of a blank screen when the entry chunk fails', async ({
  page,
}) => {
  await page.route('**/src/main.tsx', async (route) => {
    await route.abort('connectionfailed')
  })

  await page.goto('/login')

  await expect(page.getByRole('heading', { name: '页面连接没有完成' })).toBeVisible({
    timeout: 10_000,
  })
  await expect(page.getByRole('button', { name: '重新加载页面' })).toBeVisible()
  await expect(page.getByRole('link', { name: '返回固定访问入口' })).toHaveAttribute(
    'href',
    'https://chenxl916.github.io/Shujufenxi_1/',
  )
})
