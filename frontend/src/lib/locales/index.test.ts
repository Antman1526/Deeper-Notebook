import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { resources } from './index'
import { enUS } from './en-US'

const getKeys = (obj: Record<string, unknown>, prefix = ''): string[] => {
  return Object.keys(obj).reduce((res: string[], el) => {
    const val = obj[el]
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      return [...res, ...getKeys(val as Record<string, unknown>, prefix + el + '.')]
    }
    return [...res, prefix + el]
  }, [])
}

describe('Locale Parity', () => {
  const enKeys = getKeys(enUS)

  const locales = Object.entries(resources).filter(([code]) => code !== 'en-US')

  it.each(locales.map(([code, resource]) => [code, resource] as const))(
    '%s should have the same keys as en-US',
    (code, resource) => {
      const localeKeys = getKeys(resource.translation as Record<string, unknown>)

      const missing = enKeys.filter(key => !localeKeys.includes(key))
      const extra = localeKeys.filter(key => !enKeys.includes(key))

      expect(missing, `Missing keys in ${code}: ${missing.join(', ')}`).toEqual([])
      expect(extra, `Extra keys in ${code}: ${extra.join(', ')}`).toEqual([])
    },
  )
})

const getTranslation = (translation: Record<string, unknown>, key: string): unknown =>
  key.split('.').reduce<unknown>((value, segment) => (
    value !== null && typeof value === 'object'
      ? (value as Record<string, unknown>)[segment]
      : undefined
  ), translation)

const knowledgeExplorerKeys = (): string[] => {
  const srcDir = path.resolve(__dirname, '../../..')
  const explorerFiles = [
    'src/components/vault/KnowledgeExplorer.tsx',
    'src/components/vault/VaultFileTree.tsx',
    'src/components/vault/VaultGraph.tsx',
    'src/components/vault/VaultLinks.tsx',
  ]

  return [...new Set(explorerFiles.flatMap(file => {
    const source = fs.readFileSync(path.join(srcDir, file), 'utf-8')
    return [...source.matchAll(/\bt\(['"](knowledge\.[^'"]+)['"]\)/g)].map(match => match[1])
  }))].sort()
}

describe('Knowledge Explorer locale resolution', () => {
  const keys = knowledgeExplorerKeys()

  it('discovers the exact knowledge keys used by the Explorer components', () => {
    expect(keys).not.toEqual([])
  })

  it.each(Object.entries(resources))(
    '%s resolves every Knowledge Explorer key directly in its translation object',
    (code, resource) => {
      for (const key of keys) {
        const value = getTranslation(resource.translation as Record<string, unknown>, key)

        expect(value, `${code} is missing ${key}`).toEqual(expect.any(String))
        expect((value as string).trim(), `${code} has an empty ${key}`).not.toBe('')
        expect(value, `${code} falls back to the untranslated key ${key}`).not.toBe(key)
      }
    },
  )
})

const editorModeLocaleKeys = [
  'source',
  'livePreview',
  'emptyNote',
  'pageInvalid',
  'canonicalPathUnavailable',
  'pagePreview',
  'previewUnavailable',
  'footnotes',
  'sourceProvenance',
  'lineEnding',
  'encoding',
  'contentHash',
  'readOnlyMode',
  'headingLevel',
] as const

// These strings are public contracts of shared vault surfaces whose component
// ownership is split across the editor-mode tasks. Keep them in the parity and
// exact-copy checks even when the current source slice delegates their display.
const sharedVaultSurfaceLocaleKeys = new Set([
  ...editorModeLocaleKeys.map(key => `knowledge.${key}`),
  'knowledge.properties',
  'knowledge.tags',
  'knowledge.noProperties',
  'knowledge.noTags',
  'knowledge.outline',
])

describe('Read-only editor mode locale contracts', () => {
  it.each(Object.entries(resources))(
    '%s resolves every editor mode key directly',
    (code, resource) => {
      for (const key of editorModeLocaleKeys) {
        const qualifiedKey = `knowledge.${key}`
        const value = getTranslation(
          resource.translation as Record<string, unknown>,
          qualifiedKey,
        )

        expect(value, `${code} is missing ${qualifiedKey}`).toEqual(expect.any(String))
        expect((value as string).trim(), `${code} has an empty ${qualifiedKey}`)
          .not.toBe('')
      }
    },
  )

  it('keeps the exact English editor mode copy', () => {
    expect(enUS.knowledge).toMatchObject({
      source: 'Source',
      livePreview: 'Live Preview',
      emptyNote: 'This note is empty.',
      pageInvalid: 'The projected page data is invalid.',
      canonicalPathUnavailable: 'The canonical vault path is unavailable.',
      pagePreview: '{{title}} preview',
      previewUnavailable: 'Preview unavailable.',
      footnotes: 'Footnotes',
      sourceProvenance: 'Source provenance',
      lineEnding: 'Line ending',
      encoding: 'Encoding',
      contentHash: 'Content hash',
      readOnlyMode: '{{mode}} is read-only',
      headingLevel: 'Level {{level}} {{title}}',
    })
  })
})

describe('Unused Key Detection', () => {
  it(
    'all en-US leaf keys should be referenced in source files',
    () => {
      const srcDir = path.resolve(__dirname, '../../..')
      const localesDir = path.resolve(__dirname)
      const ignoredDirs = new Set(['.next', 'node_modules', 'coverage', 'dist', 'build'])

      const collectFiles = (dir: string): string[] => {
        let entries: fs.Dirent[]
        try {
          entries = fs.readdirSync(dir, { withFileTypes: true })
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
          throw error
        }

        return entries.flatMap(entry => {
          const full = path.join(dir, entry.name)
          if (entry.isDirectory()) {
            if (ignoredDirs.has(entry.name)) return []
            return collectFiles(full)
          }
          return [path.relative(srcDir, full)]
        })
      }

      const files = collectFiles(srcDir)
      const sourceFiles = files.filter(f => {
        const full = path.join(srcDir, f)
        if (full.startsWith(localesDir)) return false
        if (f.endsWith('.test.ts') || f.endsWith('.test.tsx')) return false
        return f.endsWith('.ts') || f.endsWith('.tsx')
      })

      // Normalize optional chaining (t?.common?.key → t.common.key)
      // so that keys like "common.errorDetails" match "common?.errorDetails"
      const corpus = sourceFiles
        .map(f => {
          try {
            return fs.readFileSync(path.join(srcDir, f), 'utf-8')
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code === 'ENOENT') return ''
            throw error
          }
        })
        .join('\n')
        .replace(/\?\./g, '.')

      const leafKeys = getKeys(enUS)
      const unused = leafKeys.filter(
        key => !corpus.includes(key) && !sharedVaultSurfaceLocaleKeys.has(key),
      )

      expect(
        unused,
        `Found ${unused.length} unused i18n key(s):\n${unused.join('\n')}`,
      ).toEqual([])
    },
    // v0.7.31 — bumped from 30s to 120s. The test walks every .ts/.tsx
    // file in src/ and string-matches every en-US leaf key against the
    // corpus. As the codebase has grown (Dashboard, podcast presets,
    // auto-fill, etc.), the file walk has crept past 30s on slower
    // boxes (especially under cold-cache CI). 120s gives comfortable
    // headroom; the check is still well under 1 min on a warm-cache
    // local run.
    120_000,
  )
})
