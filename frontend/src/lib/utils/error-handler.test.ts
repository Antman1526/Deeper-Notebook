/**
 * v0.7.196 — Regression test for the bare-getApiErrorKey leak bug.
 *
 * `getApiErrorKey(error, t('common.error'))` returns the i18n KEY
 * string (e.g. `"apiErrors.notebookNotFound"`). When passed directly
 * as a toast/alert description without wrapping in `t(...)`, the
 * user sees the literal key text rendered in the UI on mapped
 * errors.
 *
 * The visual audit found 27 callsites across 6 hook files using
 * this pattern. v0.7.196 swapped them to `getApiErrorMessage(error,
 * t, 'common.error')` which returns the *translated* string (or the
 * backend's detail string when no mapping exists).
 *
 * This test pins the invariant:
 *
 *   - No source file under src/lib/hooks/ may use
 *     `getApiErrorKey(` directly on a `description:` field. Either
 *     wrap in `t(getApiErrorKey(...))` or use `getApiErrorMessage(...)`.
 *
 * The error-handler.ts module itself is excluded (it defines the
 * helpers). CLAUDE.md docs are excluded (description, not code).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

import {
  getApiErrorKey,
  getApiErrorMessage,
  formatApiError,
} from './error-handler'

const HOOKS_ROOT = join(__dirname, '..', 'hooks')

function walkTsFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) {
      walkTsFiles(full, out)
    } else if (
      (name.endsWith('.ts') || name.endsWith('.tsx')) &&
      !name.endsWith('.test.ts') &&
      !name.endsWith('.test.tsx')
    ) {
      out.push(full)
    }
  }
  return out
}

describe('error-handler — translating variant', () => {
  it('getApiErrorMessage returns translated string for mapped errors', () => {
    const fakeT = (key: string) => `T(${key})`
    const out = getApiErrorMessage(
      { response: { data: { detail: 'Notebook not found' } } },
      fakeT,
    )
    // The mapped key apiErrors.notebookNotFound is passed through t().
    expect(out).toBe('T(apiErrors.notebookNotFound)')
  })

  it('getApiErrorMessage returns backend detail when no mapping exists', () => {
    const fakeT = (key: string) => `T(${key})`
    const out = getApiErrorMessage(
      { response: { data: { detail: 'Something unmapped happened' } } },
      fakeT,
    )
    expect(out).toBe('Something unmapped happened')
  })

  it('getApiErrorMessage falls back to translated fallback key on empty-string detail', () => {
    // formatApiError('') returns '' (string short-circuit). The
    // falsy-message branch then translates the fallback key.
    const fakeT = (key: string) => `T(${key})`
    const out = getApiErrorMessage('', fakeT, 'common.error')
    expect(out).toBe('T(common.error)')
  })

  it('getApiErrorMessage surfaces the default "unexpected" string for null/undefined', () => {
    // formatApiError(null) returns the literal "An unexpected error
    // occurred"; that string then matches nothing in ERROR_MAP and
    // is shown to the user as-is. This is the safe default — the
    // fallback key only kicks in for truly empty detail.
    const fakeT = (key: string) => `T(${key})`
    expect(getApiErrorMessage(null, fakeT, 'common.error')).toBe(
      'An unexpected error occurred',
    )
  })

  it('formatApiError handles axios-style and bare-Error shapes', () => {
    expect(
      formatApiError({ response: { data: { detail: 'axios path' } } }),
    ).toBe('axios path')
    expect(formatApiError(new Error('bare path'))).toBe('bare path')
    expect(formatApiError('string path')).toBe('string path')
    expect(formatApiError(null)).toBe('An unexpected error occurred')
  })

  it('getApiErrorKey still returns a KEY (must not be used directly in UI)', () => {
    // This documents why direct-use of getApiErrorKey is a bug:
    // it returns the key STRING, not the translated text.
    const out = getApiErrorKey({
      response: { data: { detail: 'Notebook not found' } },
    })
    expect(out).toBe('apiErrors.notebookNotFound')
  })
})

describe('v0.7.196 — no bare getApiErrorKey in toast descriptions', () => {
  it('hook files do not pass getApiErrorKey(...) directly as a description', () => {
    const offenders: { file: string; line: number; text: string }[] = []
    const files = walkTsFiles(HOOKS_ROOT)

    for (const file of files) {
      const src = readFileSync(file, 'utf-8')
      const lines = src.split('\n')
      lines.forEach((line, idx) => {
        // The bug pattern: a `description:` field whose value starts
        // with `getApiErrorKey(` (NOT wrapped in `t(...)`). We use a
        // narrow regex so we don't false-positive on
        //   - `description: t(getApiErrorKey(...))` ✓ correct (wrapped)
        //   - `description: getApiErrorMessage(...)` ✓ correct (translating helper)
        //   - lines that mention getApiErrorKey in comments / imports
        const m = /description:\s*getApiErrorKey\s*\(/.exec(line)
        if (m) {
          offenders.push({ file, line: idx + 1, text: line.trim() })
        }
      })
    }

    if (offenders.length > 0) {
      const detail = offenders
        .map((o) => `  ${o.file}:${o.line} → ${o.text}`)
        .join('\n')
      throw new Error(
        `v0.7.196 regression — ${offenders.length} hook callsite(s) are ` +
          `passing getApiErrorKey() directly as a toast description. The ` +
          `user will see the literal i18n key as text on mapped errors. ` +
          `Use getApiErrorMessage(error, t, '<fallback-key>') instead.\n` +
          detail,
      )
    }
  })
})
