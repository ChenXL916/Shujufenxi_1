import { readdir, stat } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const limitBytes = 650 * 1024
const assetsDirectory = path.resolve(process.cwd(), 'dist/assets')

const assetNames = (await readdir(assetsDirectory)).filter((name) => name.endsWith('.js'))
const assets = await Promise.all(
  assetNames.map(async (name) => ({
    name,
    bytes: (await stat(path.join(assetsDirectory, name))).size,
  })),
)
assets.sort((left, right) => right.bytes - left.bytes)

const violations = assets.filter((asset) => asset.bytes > limitBytes)
const largest = assets.slice(0, 8).map((asset) => ({
  chunk: asset.name,
  kib: Number((asset.bytes / 1024).toFixed(2)),
}))

console.table(largest)
if (violations.length > 0) {
  console.error(`Chunk audit failed: ${violations.length} JavaScript chunk(s) exceed 650 KiB.`)
  process.exit(1)
}

console.log(`Chunk audit passed: ${assets.length} JavaScript chunks, all <= 650 KiB.`)
