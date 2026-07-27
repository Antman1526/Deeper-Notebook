import { describe, expect, it } from 'vitest'

import { resources } from './locales'

describe('Deeper Notebook export locale labels', () => {
  it('uses Deeper Notebook rather than the legacy ONP brand in every export default', () => {
    for (const [locale, resource] of Object.entries(resources)) {
      expect(resource.translation.filesystem.defaultExports, locale).not.toMatch(/\bONP\b/i)
      expect(resource.translation.filesystem.defaultExports, locale).toMatch(/Deeper Notebook/i)
    }
  })
})
