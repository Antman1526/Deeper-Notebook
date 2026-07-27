import fs from 'fs'
import path from 'path'
import { describe, expect, it } from 'vitest'

import { resources } from './locales'

const SRC = path.resolve(__dirname, '..')
const REQUIRED_LOCALES = [
  'bn-IN',
  'ca-ES',
  'de-DE',
  'en-US',
  'es-ES',
  'fr-FR',
  'it-IT',
  'ja-JP',
  'pl-PL',
  'pt-BR',
  'ru-RU',
  'tr-TR',
  'zh-CN',
  'zh-TW',
] as const
const ACTIVE_IDENTITY_SOURCES = [
  'app/layout.tsx',
  'app/(dashboard)/page.tsx',
  'components/intro/IntroReveal.tsx',
  'components/layout/AppSidebar.tsx',
] as const
const STALE_PRODUCT_LABEL =
  /Open Notebook Plus|Open notebook\+|Open Notebook\+|Open Notebook/

describe('Task 6 active Deeper Notebook identity', () => {
  it('defines the exact required locale set', () => {
    expect(Object.keys(resources).sort()).toEqual([...REQUIRED_LOCALES].sort())
  })

  it('uses the exact product name in every required locale without stale labels', () => {
    for (const [locale, resource] of Object.entries(resources)) {
      expect(resource.translation.common.appName, locale).toBe('Deeper Notebook')
      expect(JSON.stringify(resource.translation), locale).not.toMatch(STALE_PRODUCT_LABEL)
    }
  })

  it('keeps stale product labels out of the active identity source inventory', () => {
    for (const relativePath of ACTIVE_IDENTITY_SOURCES) {
      const source = fs.readFileSync(path.join(SRC, relativePath), 'utf8')
      expect(source, relativePath).not.toMatch(STALE_PRODUCT_LABEL)
    }
  })

  it('uses the canonical fetch helper and Gmail namespace in active components', () => {
    const helper = path.join(SRC, 'lib/api/deeper-notebook.ts')
    expect(fs.existsSync(helper)).toBe(true)
    expect(fs.readFileSync(helper, 'utf8')).toContain('deeperNotebookFetch')

    for (const relativePath of [
      'components/deeper-notebook/ThemeSwitcher.tsx',
      'components/deeper-notebook/GmailIntegration.tsx',
      'components/deeper-notebook/GmailSidebarButton.tsx',
    ]) {
      const source = fs.readFileSync(path.join(SRC, relativePath), 'utf8')
      expect(source, relativePath).toContain('deeperNotebookFetch')
      expect(source, relativePath).not.toContain('onpFetch')
      expect(source, relativePath).not.toContain('/api/onp/')
    }
  })
})
