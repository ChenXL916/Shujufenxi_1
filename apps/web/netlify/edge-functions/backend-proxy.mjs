const REGISTRY_URL =
  'https://raw.githubusercontent.com/ChenXL916/Shujufenxi_1/liveops-runtime/runtime/backend-origin.json'
const REGISTRY_CACHE_MS = 15_000
const REQUEST_TIMEOUT_MS = 60_000

let cachedOrigin = null
let cacheExpiresAt = 0

export function normalizeBackendOrigin(rawOrigin) {
  const value = rawOrigin?.trim()
  if (!value) throw new Error('运行网关尚未发布')

  const url = new URL(value)
  if (
    url.protocol !== 'https:' ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.pathname !== '/' && url.pathname !== '') ||
    !url.hostname.endsWith('.trycloudflare.com')
  ) {
    throw new Error('运行网关地址不合法')
  }
  return url.origin
}

export function resetOriginCacheForTests() {
  cachedOrigin = null
  cacheExpiresAt = 0
}

async function currentBackendOrigin() {
  const now = Date.now()
  if (cachedOrigin && cacheExpiresAt > now) return cachedOrigin

  const cacheBucket = Math.floor(now / 30_000)
  const response = await fetch(`${REGISTRY_URL}?v=${cacheBucket}`, {
    headers: { accept: 'application/json' },
    cache: 'no-store',
    signal: AbortSignal.timeout(8_000),
  })
  if (!response.ok) throw new Error(`运行网关查询失败：HTTP ${response.status}`)
  const payload = await response.json()
  const origin = normalizeBackendOrigin(payload.origin)
  cachedOrigin = origin
  cacheExpiresAt = now + REGISTRY_CACHE_MS
  return origin
}

function proxyError(message) {
  return Response.json(
    {
      detail: '后台网关正在恢复，请稍后重试',
      gateway_error: message,
    },
    {
      status: 503,
      headers: {
        'cache-control': 'no-store',
        'retry-after': '15',
      },
    },
  )
}

export default async function backendProxy(request) {
  try {
    const incomingUrl = new URL(request.url)
    const allowedPath =
      incomingUrl.pathname.startsWith('/api/') ||
      incomingUrl.pathname.startsWith('/auth/') ||
      incomingUrl.pathname === '/health' ||
      incomingUrl.pathname === '/ready'
    if (!allowedPath) return new Response('Not found', { status: 404 })

    const origin = await currentBackendOrigin()
    const targetUrl = new URL(`${incomingUrl.pathname}${incomingUrl.search}`, origin)
    const headers = new Headers(request.headers)
    for (const name of ['host', 'connection', 'content-length', 'transfer-encoding']) {
      headers.delete(name)
    }
    headers.set('x-forwarded-host', incomingUrl.host)
    headers.set('x-forwarded-proto', 'https')
    headers.set('x-liveops-gateway', 'netlify-edge')

    const hasBody = request.method !== 'GET' && request.method !== 'HEAD'
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: 'manual',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
    const responseHeaders = new Headers(upstream.headers)
    responseHeaders.delete('content-length')
    responseHeaders.delete('transfer-encoding')
    responseHeaders.set('cache-control', 'no-store')
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown gateway error'
    return proxyError(message)
  }
}
