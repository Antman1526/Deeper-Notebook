import type { TFunction } from 'i18next'
import { describe, expect, it } from 'vitest'

import { CREATE_TARGETS, getNavigation } from '@/components/layout/AppSidebar'

describe('Luminous Folio navigation parity contract', () => {
  it('preserves the existing navigation href order and create targets', () => {
    const previousFlag = process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '1'
    const t = ((key: string) => key) as TFunction
    try {
      const sections = getNavigation(t)

      expect(sections.flatMap(section => section.items.map(item => item.href))).toEqual([
        '/sources', '/capture', '/notebooks', '/knowledge', '/search',
        '/studio', '/podcasts', '/study', '/settings/api-keys',
        '/transformations', '/settings', '/settings/mcp',
        '/settings/launcher-prefs', '/advanced',
      ])
      expect(CREATE_TARGETS).toEqual(['source', 'notebook', 'podcast'])
    } finally {
      if (previousFlag === undefined) delete process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH
      else process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = previousFlag
    }
  })
})
