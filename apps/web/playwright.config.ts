import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../..')
const databaseUrl = `sqlite+pysqlite:///${path.join(root, 'e2e.db').replace(/\\/g, '/')}`
const apiPython = path.join(root, 'apps', 'api', '.venv', 'Scripts', 'python.exe')
const apiVirtualEnv = path.join(root, 'apps', 'api', '.venv')
const apiPythonPath = path.join(root, 'apps', 'api')
const apiPort = Number(process.env.E2E_API_PORT ?? '18000')
const webPort = Number(process.env.E2E_WEB_PORT ?? '4173')

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: `http://127.0.0.1:${webPort}`, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${apiPython}" ../../scripts/prepare_e2e.py && "${apiPython}" -m uvicorn app.main:app --app-dir ../api --host 127.0.0.1 --port ${apiPort}`,
      port: apiPort,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        APP_ENV: 'test',
        DATABASE_URL: databaseUrl,
        DEV_AUTH_BYPASS: 'true',
        FEISHU_APP_ID: '',
        FEISHU_APP_SECRET: '',
        FEISHU_BOT_WEBHOOK_URL: '',
        FEISHU_BOT_SECRET: '',
        FEISHU_BOT_CHAT_ID: '',
        PYTHONUTF8: '1',
        PYTHONPATH: apiPythonPath,
        VIRTUAL_ENV: apiVirtualEnv,
      },
    },
    {
      command: `npm run dev -- --port ${webPort}`,
      port: webPort,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { ...process.env, VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
    },
  ],
})
