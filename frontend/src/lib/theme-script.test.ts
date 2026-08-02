import { describe, expect, it } from 'vitest'
import { themeScript } from './theme-script'

describe('pre-hydration Research Core theme script', () => {
  it('prefers canonical storage, then legacy, then old Zustand storage', () => {
    expect(themeScript.indexOf("getItem('dn-theme')")).toBeLessThan(themeScript.indexOf("getItem('onp-theme')"))
    expect(themeScript.indexOf("getItem('onp-theme')")).toBeLessThan(themeScript.indexOf("getItem('theme-storage')"))
  })

  it('falls back to Research Core Dark and sets dark class from the catalog', () => {
    expect(themeScript).toContain("'research-core-dark'")
    expect(themeScript).toContain('research-core-dark')
    expect(themeScript).toContain("classList.toggle('dark'")
  })

  it('normalizes legacy light values and rejects unknown theme IDs', () => {
    expect(themeScript).toContain("theme === 'light'")
    expect(themeScript).toContain("theme = 'light-blue'")
    expect(themeScript).toContain('validThemes.includes(theme)')
  })
})
