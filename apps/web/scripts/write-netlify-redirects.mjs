import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

function normalizeBackendOrigin(rawOrigin) {
  const value = rawOrigin?.trim()
  if (!value) return null

  const url = new URL(value)
  if (url.protocol !== 'https:') {
    throw new Error('NETLIFY_BACKEND_ORIGIN must use HTTPS')
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error('NETLIFY_BACKEND_ORIGIN must be an origin without credentials, query, or hash')
  }
  if (url.pathname !== '/' && url.pathname !== '') {
    throw new Error('NETLIFY_BACKEND_ORIGIN must not include a path')
  }
  return url.origin
}

function buildRedirects(backendOrigin) {
  const lines = []
  if (backendOrigin) {
    lines.push(
      `/api/*  ${backendOrigin}/api/:splat  200`,
      `/auth/*  ${backendOrigin}/auth/:splat  200`,
      `/health  ${backendOrigin}/health  200`,
      `/ready  ${backendOrigin}/ready  200`,
    )
  } else {
    lines.push('# NETLIFY_BACKEND_ORIGIN is not set; only the static dashboard is available.')
  }
  lines.push('/*  /index.html  200', '')
  return lines.join('\n')
}

const backendOrigin = normalizeBackendOrigin(process.env.NETLIFY_BACKEND_ORIGIN)
const outputPath = resolve(process.cwd(), process.env.NETLIFY_REDIRECTS_OUTPUT ?? 'dist/_redirects')

mkdirSync(dirname(outputPath), { recursive: true })
writeFileSync(outputPath, buildRedirects(backendOrigin), 'utf8')

console.log(
  backendOrigin
    ? `Netlify redirects configured for backend ${backendOrigin}`
    : 'Netlify redirects configured for SPA-only deployment',
)
