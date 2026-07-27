import fs from 'fs'
import path from 'path'
import { describe, expect, it } from 'vitest'

import { resources } from './locales'

const SRC = path.resolve(__dirname, '..')

describe('Task 6 active Deeper Notebook identity', () => {
  it('uses the exact product name in every locale without stale active labels', () => {
    for (const [locale, resource] of Object.entries(resources)) {
      expect(resource.translation.common.appName, locale).toBe('Deeper Notebook')
      expect(JSON.stringify(resource.translation), locale).not.toMatch(
        /Open Notebook Plus|Open notebook\+|Open Notebook\+|Open Notebook/,
      )
    }
  })

  it('uses the approved metadata, dashboard, intro, and sidebar copy', () => {
    const layout = fs.readFileSync(path.join(SRC, 'app/layout.tsx'), 'utf8')
    const dashboard = fs.readFileSync(
      path.join(SRC, 'app/(dashboard)/page.tsx'),
      'utf8',
    )
    const intro = fs.readFileSync(
      path.join(SRC, 'components/intro/IntroReveal.tsx'),
      'utf8',
    )
    const sidebar = fs.readFileSync(
      path.join(SRC, 'components/layout/AppSidebar.tsx'),
      'utf8',
    )

    expect(layout).toContain('title: "Deeper Notebook"')
    expect(layout).toContain(
      'description: "Local-first research and knowledge workspace"',
    )
    expect(dashboard).toContain('Deeper Notebook')
    expect(dashboard).toContain('Think further with every source')
    expect(intro).toContain('aria-label="Deeper Notebook"')
    expect(sidebar).toContain('alt="Deeper Notebook"')
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
