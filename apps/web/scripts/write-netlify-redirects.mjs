import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

const outputPath = resolve(process.cwd(), process.env.NETLIFY_REDIRECTS_OUTPUT ?? 'dist/_redirects')

mkdirSync(dirname(outputPath), { recursive: true })
writeFileSync(
  outputPath,
  [
    '# API and auth paths are handled by the Netlify backend-proxy edge function.',
    '/*  /index.html  200',
    '',
  ].join('\n'),
  'utf8',
)

console.log('Netlify redirects configured with SPA fallback after the edge gateway')
