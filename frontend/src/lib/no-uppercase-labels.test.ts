import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// v0.8.130 — Design rule (product owner, 2026-10-01): eyebrows, field labels and
// section headings are quiet, sentence-case grey text. The copy in the locale
// files is already sentence case; the caps used to come from the Tailwind
// `uppercase` utility in className strings. This pins that nobody puts it back.
//
// The scan is deliberately line based: any non-comment line of a non-test .tsx
// file that contains the `uppercase` token (string literal, template literal or
// a cn()/clsx argument alike) is a failure, unless it is covered below.
const SRC = path.resolve(__dirname, '..')

// Semantic uppercase only: content that is not words in a sentence (key caps,
// format badges fed by data like "pdf"/"mp3", monograms, locale codes, hashes).
// Each entry is a path relative to src/ plus the reason it may keep the utility.
const ALLOWLIST: ReadonlyArray<{ file: string; reason: string }> = []

const allowed = new Set(ALLOWLIST.map((entry) => entry.file))

function collectTsx(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules') continue
      collectTsx(full, out)
    } else if (entry.name.endsWith('.tsx') && !/\.test\.tsx$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

const isCommentLine = (line: string) => /^\s*(\/\/|\/\*|\*|\{\s*\/\*)/.test(line)

describe('sentence-case labels', () => {
  it('no component sets the `uppercase` utility outside the commented allowlist', () => {
    const offenders: string[] = []
    for (const file of collectTsx(SRC)) {
      const rel = path.relative(SRC, file).split(path.sep).join('/')
      if (allowed.has(rel)) continue
      fs.readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line, index) => {
          if (isCommentLine(line)) return
          if (/(?<![\w-])uppercase(?![\w-])/.test(line)) offenders.push(`${rel}:${index + 1}`)
        })
    }
    expect(offenders, `labels must be sentence case; remove \`uppercase\`:\n${offenders.join('\n')}`).toEqual([])
  })

  it('every allowlist entry still exists and still needs its exemption', () => {
    for (const { file, reason } of ALLOWLIST) {
      expect(reason.length, `${file} needs a reason`).toBeGreaterThan(0)
      const source = fs.readFileSync(path.join(SRC, file), 'utf8')
      expect(source, `${file} no longer uses uppercase; drop it from the allowlist`).toMatch(
        /(?<![\w-])uppercase(?![\w-])/,
      )
    }
  })
})
