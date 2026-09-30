import { createReadStream, existsSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { createGzip } from 'node:zlib'
import { pipeline } from 'node:stream/promises'
import { Writable } from 'node:stream'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const manifestPath = join(dist, '.vite', 'manifest.json')
const maxInitialGzip = Number(process.env.BUNDLE_INITIAL_GZIP_KB || 650) * 1024
const maxChunkGzip = Number(process.env.BUNDLE_MAX_CHUNK_GZIP_KB || 300) * 1024

if (!existsSync(manifestPath)) {
  throw new Error(`Vite manifest not found: ${manifestPath}. Run npm run build first.`)
}

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))

async function gzipSize(path) {
  let size = 0
  await pipeline(createReadStream(path), createGzip(), new Writable({
    write(chunk, _encoding, callback) {
      size += chunk.length
      callback()
    },
  }))
  return size
}

function collectInitial(entryKey) {
  const visited = new Set()
  const files = new Set()
  const visit = (key) => {
    if (!key || visited.has(key)) return
    visited.add(key)
    const item = manifest[key]
    if (!item) return
    if (item.file?.endsWith('.js')) files.add(item.file)
    for (const css of item.css || []) files.add(css)
    for (const dependency of item.imports || []) visit(dependency)
  }
  visit(entryKey)
  return files
}

const entry = Object.entries(manifest).find(([, value]) => value.isEntry)
if (!entry) throw new Error('No entry chunk found in Vite manifest')

const initialFiles = collectInitial(entry[0])
const initial = []
for (const file of initialFiles) {
  const path = join(dist, file)
  initial.push({ file, raw: statSync(path).size, gzip: await gzipSize(path) })
}

const chunks = []
for (const value of Object.values(manifest)) {
  if (!value.file?.endsWith('.js')) continue
  const path = join(dist, value.file)
  if (chunks.some((row) => row.file === value.file)) continue
  chunks.push({ file: value.file, raw: statSync(path).size, gzip: await gzipSize(path) })
}

const initialGzip = initial.reduce((total, item) => total + item.gzip, 0)
const largest = chunks.sort((a, b) => b.gzip - a.gzip)[0]
const kb = (bytes) => (bytes / 1024).toFixed(2)
const report = {
  entry: entry[0],
  initial_gzip_kb: Number(kb(initialGzip)),
  initial_budget_gzip_kb: Number(kb(maxInitialGzip)),
  largest_chunk: largest ? { file: largest.file, gzip_kb: Number(kb(largest.gzip)) } : null,
  chunk_budget_gzip_kb: Number(kb(maxChunkGzip)),
  initial_files: initial.map((item) => ({ file: item.file, gzip_kb: Number(kb(item.gzip)) })),
}
console.log(JSON.stringify(report, null, 2))
writeFileSync(join(dist, 'bundle-budget.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')

const failures = []
if (initialGzip > maxInitialGzip) failures.push(`initial resources ${kb(initialGzip)} KB > ${kb(maxInitialGzip)} KB`)
if (largest?.gzip > maxChunkGzip) failures.push(`chunk ${largest.file} ${kb(largest.gzip)} KB > ${kb(maxChunkGzip)} KB`)
if (failures.length) {
  console.error(`Bundle budget failed: ${failures.join('; ')}`)
  process.exit(1)
}
