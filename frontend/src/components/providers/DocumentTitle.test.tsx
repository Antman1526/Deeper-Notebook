import { describe, expect, it } from 'vitest'

import { routeTitleKey } from './DocumentTitle'

describe('routeTitleKey', () => {
  it('names a route by its most specific prefix', () => {
    expect(routeTitleKey('/settings/mcp')).toBe('settings.mcp.navTitle')
    expect(routeTitleKey('/settings')).toBe('navigation.settings')
    expect(routeTitleKey('/podcasts/studio')).toBe('podcasts.podcastStudio.title')
    expect(routeTitleKey('/notebooks/notebook:abc')).toBe('navigation.notebooks')
  })

  it('leaves the brand alone where no route title applies', () => {
    expect(routeTitleKey('/')).toBeNull()
    expect(routeTitleKey('/login')).toBeNull()
    expect(routeTitleKey('/notebooksx')).toBeNull()
    expect(routeTitleKey(null)).toBeNull()
  })
})
