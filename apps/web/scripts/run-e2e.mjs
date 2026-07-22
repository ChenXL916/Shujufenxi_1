import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const webRoot = path.resolve(here, '..')
const root = path.resolve(webRoot, '../..')
const apiPython =
  process.env.E2E_PYTHON ??
  (process.platform === 'win32'
    ? path.join(root, 'apps', 'api', '.venv', 'Scripts', 'python.exe')
    : 'python')
const apiPort = Number(process.env.E2E_API_PORT ?? '18000')
const webPort = Number(process.env.E2E_WEB_PORT ?? '4173')
const databaseUrl = `sqlite+pysqlite:///${path.join(root, 'e2e.db').replace(/\\/g, '/')}`
const apiSitePackages = path.join(root, 'apps', 'api', '.venv', 'Lib', 'site-packages')
const apiEnv = {
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
  PYTHONPATH: [path.join(root, 'apps', 'api'), process.env.PYTHONPATH]
    .filter(Boolean)
    .join(path.delimiter),
  VIRTUAL_ENV:
    process.env.VIRTUAL_ENV ??
    (process.platform === 'win32' ? path.join(root, 'apps', 'api', '.venv') : ''),
}

async function stopChild(child) {
  if (!child?.pid || child.exitCode !== null) return
  const exited = new Promise((resolve) => child.once('exit', resolve))
  child.kill('SIGTERM')
  await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 5_000))])
  if (child.exitCode === null) child.kill('SIGKILL')
}

async function waitFor(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let lastError
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = new Error(`${url} returned HTTP ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`Timed out waiting for ${url}: ${String(lastError)}`)
}

const preparation = spawnSync(apiPython, [path.join(root, 'scripts', 'prepare_e2e.py')], {
  cwd: webRoot,
  env: apiEnv,
  stdio: 'inherit',
})
if (preparation.status !== 0) process.exit(preparation.status ?? 1)

const pythonProbe = spawnSync(apiPython, ['-c', 'import sys; print(sys._base_executable)'], {
  encoding: 'utf8',
})
const apiServerPython =
  process.platform === 'win32' && pythonProbe.status === 0 ? pythonProbe.stdout.trim() : apiPython
const apiServerEnv = {
  ...apiEnv,
  PYTHONPATH: [path.join(root, 'apps', 'api'), apiSitePackages, process.env.PYTHONPATH]
    .filter(Boolean)
    .join(path.delimiter),
}

const api = spawn(
  apiServerPython,
  [
    '-m',
    'uvicorn',
    'app.main:app',
    '--app-dir',
    path.join(root, 'apps', 'api'),
    '--host',
    '127.0.0.1',
    '--port',
    String(apiPort),
  ],
  { cwd: webRoot, env: apiServerEnv, stdio: 'inherit' },
)
const web = spawn(
  process.execPath,
  [
    path.join(webRoot, 'node_modules', 'vite', 'bin', 'vite.js'),
    '--host',
    '127.0.0.1',
    '--port',
    String(webPort),
    '--strictPort',
  ],
  {
    cwd: webRoot,
    env: { ...process.env, VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
    stdio: 'inherit',
  },
)

let exitCode = 1
try {
  await Promise.all([
    waitFor(`http://127.0.0.1:${apiPort}/health`, 120_000),
    waitFor(`http://127.0.0.1:${webPort}`, 60_000),
  ])
  const runner = spawn(
    process.execPath,
    [
      path.join(webRoot, 'node_modules', '@playwright', 'test', 'cli.js'),
      'test',
      ...process.argv.slice(2),
    ],
    {
      cwd: webRoot,
      env: { ...process.env, E2E_EXTERNAL_SERVERS: 'true' },
      stdio: 'inherit',
    },
  )
  exitCode = await new Promise((resolve, reject) => {
    runner.once('error', reject)
    runner.once('exit', (code) => resolve(code ?? 1))
  })
} finally {
  await Promise.all([stopChild(web), stopChild(api)])
}

process.exit(exitCode)
