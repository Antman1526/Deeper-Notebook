import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// v0.8.130 — glass blur is banned by the design rules (e2e/premium-pass.spec.ts checks the
// main pages in a browser). Overlays and rarely-seen screens escaped that check; this one
// reads the source, so a blur anywhere fails here.
const files = (dir: string): string[] =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return files(full)
    return /\.(tsx|ts|css)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : []
  })

describe('no glass blur', () => {
  it('uses no backdrop blur anywhere in the interface source', () => {
    const root = path.resolve(__dirname, '..')
    const offenders: string[] = []
    for (const file of files(root)) {
      const lines = fs.readFileSync(file, 'utf8').split('\n')
      lines.forEach((line, index) => {
        const code = line.replace(/\/\/.*$|\/\*.*?\*\//g, '')
        if (/backdrop-blur|backdrop-filter\s*:\s*blur/.test(code)) offenders.push(`${path.relative(root, file)}:${index + 1}`)
      })
    }
    expect(offenders).toEqual([])
  })
})
