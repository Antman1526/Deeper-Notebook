#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { gzipSync } from 'node:zlib'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const nextRoot = join(frontendRoot, '.next')
const receiptPath = resolve(
  process.env.SOURCE_GALLERY_BROWSER_BUDGET_RECEIPT
    ?? '/tmp/deeper-notebook-source-gallery-browser-budget.json',
)
const limits = { javascriptGzipBytes: 40 * 1024, cssGzipBytes: 24 * 1024 }
const routeManifests = [
  'server/app/(dashboard)/sources/page_client-reference-manifest.js',
  'server/app/(dashboard)/notebooks/[id]/page_client-reference-manifest.js',
  'server/app/(dashboard)/knowledge/page_client-reference-manifest.js',
  'server/app/(dashboard)/search/page_client-reference-manifest.js',
  'server/app/(dashboard)/capture/page_client-reference-manifest.js',
]

function fail(message) {
  throw new Error(`SOURCE_GALLERY_BROWSER_BUDGET: ${message}`)
}

function runBuild(label, flags) {
  const result = spawnSync('npm', ['run', 'build'], {
    cwd: frontendRoot,
    env: {
      ...process.env,
      NEXT_TELEMETRY_DISABLED: '1',
      NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2: flags.visualSystem,
      NEXT_PUBLIC_DN_SOURCE_VISUALS: flags.sourceVisuals,
    },
    stdio: 'inherit',
  })
  if (result.error) fail(`${label} build could not start: ${result.error.message}`)
  if (result.status !== 0) fail(`${label} build exited ${result.status ?? 'without a status'}`)
}

function assetRelativePath(value) {
  const match = String(value).match(/(?:\/_next\/)?(static\/chunks\/[A-Za-z0-9_.-]+\.(?:js|css))/)
  return match?.[1] ?? null
}

function collectJsonStrings(value, output) {
  if (typeof value === 'string') {
    const asset = assetRelativePath(value)
    if (asset) output.add(asset)
    return
  }
  if (Array.isArray(value)) {
    for (const item of value) collectJsonStrings(item, output)
    return
  }
  if (value && typeof value === 'object') {
    for (const item of Object.values(value)) collectJsonStrings(item, output)
  }
}

function manifestAssetPaths() {
  const paths = new Set()
  const buildManifestPath = join(nextRoot, 'build-manifest.json')
  if (!existsSync(buildManifestPath)) fail('missing .next/build-manifest.json')
  collectJsonStrings(JSON.parse(readFileSync(buildManifestPath, 'utf8')), paths)

  for (const manifest of routeManifests) {
    const manifestPath = join(nextRoot, manifest)
    if (!existsSync(manifestPath)) fail(`missing route manifest ${manifest}`)
    const source = readFileSync(manifestPath, 'utf8')
    for (const match of source.matchAll(/(?:\/_next\/)?(static\/chunks\/[A-Za-z0-9_.-]+\.(?:js|css))/g)) {
      paths.add(match[1])
    }
  }
  return [...paths].sort()
}

function snapshot(label, flags) {
  runBuild(label, flags)
  const assets = new Map()
  for (const assetPath of manifestAssetPaths()) {
    const absolute = resolve(nextRoot, assetPath)
    if (isAbsolute(assetPath) || relative(nextRoot, absolute).startsWith(`..${sep}`)) {
      fail(`manifest asset escaped .next: ${assetPath}`)
    }
    if (!existsSync(absolute)) fail(`manifest asset is missing: ${assetPath}`)
    const bytes = readFileSync(absolute)
    assets.set(assetPath, {
      bytes,
      sha256: createHash('sha256').update(bytes).digest('hex'),
      type: assetPath.endsWith('.css') ? 'css' : 'javascript',
    })
  }
  return { label, flags, assets }
}

function changedAssets(before, after) {
  const beforeHashes = new Set([...before.assets.values()].map(asset => asset.sha256))
  const afterHashes = new Set([...after.assets.values()].map(asset => asset.sha256))
  const added = [...after.assets.entries()]
    .filter(([, asset]) => !beforeHashes.has(asset.sha256))
  const removed = [...before.assets.entries()]
    .filter(([, asset]) => !afterHashes.has(asset.sha256))
  return { added, removed }
}

function measure(entries) {
  return entries.map(([path, asset]) => ({
    path,
    type: asset.type,
    sha256: asset.sha256,
    rawBytes: asset.bytes.length,
    gzipBytes: gzipSync(asset.bytes, { level: 9 }).length,
  }))
}

function totalByType(entries, type) {
  return entries
    .filter(entry => entry.type === type)
    .reduce((total, entry) => total + entry.gzipBytes, 0)
}

const phase1Flags = { visualSystem: '1', sourceVisuals: '0' }
const phase2aFlags = { visualSystem: '1', sourceVisuals: '1' }
const phase1 = snapshot('phase1', phase1Flags)
const phase2a = snapshot('phase2a', phase2aFlags)
const changes = changedAssets(phase1, phase2a)
const added = measure(changes.added)
const removed = measure(changes.removed)
const javascriptDelta = totalByType(added, 'javascript') - totalByType(removed, 'javascript')
const cssDelta = totalByType(added, 'css') - totalByType(removed, 'css')

const receipt = {
  schema: 'deeper-notebook.source-gallery-browser-budget.v1',
  comparison: {
    phase1: { flags: phase1Flags, manifestAssetCount: phase1.assets.size },
    phase2a: { flags: phase2aFlags, manifestAssetCount: phase2a.assets.size },
  },
  changedAssets: { added, removed },
  gzipDeltaBytes: { javascript: javascriptDelta, css: cssDelta },
  limitsBytes: { javascript: limits.javascriptGzipBytes, css: limits.cssGzipBytes },
  passed: javascriptDelta <= limits.javascriptGzipBytes && cssDelta <= limits.cssGzipBytes,
}

const temporaryReceipt = `${receiptPath}.tmp-${process.pid}`
writeFileSync(temporaryReceipt, `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 })
renameSync(temporaryReceipt, receiptPath)
process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`)

if (!receipt.passed) {
  fail(`gzip delta exceeded limits: JS ${javascriptDelta}/${limits.javascriptGzipBytes}, CSS ${cssDelta}/${limits.cssGzipBytes}`)
}
