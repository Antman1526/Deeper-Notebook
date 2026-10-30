import { describe, expect, it } from 'vitest'

import { GUIDED_TIPS, getGuidedTipForPath } from './catalog'

describe('Guided Tips catalog', () => {
  it('covers the approved major sections with stable unique IDs', () => {
    expect(GUIDED_TIPS.map(tip => tip.id)).toEqual([
      'dashboard-overview', 'sources-overview', 'capture-overview',
      'notebooks-overview', 'knowledge-overview', 'search-overview',
      'studio-overview', 'podcasts-overview', 'study-overview',
      'models-overview', 'settings-overview',
    ])
    expect(new Set(GUIDED_TIPS.map(tip => tip.id)).size).toBe(GUIDED_TIPS.length)
    // v0.8.130 — Phase 3b: the V2 shell has one rail, not the Instrument Dock. The version
    // stays 2 so people who already dismissed the tip are not shown it again.
    expect(GUIDED_TIPS.find(tip => tip.id === 'dashboard-overview')).toMatchObject({
      version: 2,
      titleKey: 'workspace.catalog.dashboardOverviewTitle',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'knowledge-overview')).toMatchObject({
      version: 2,
      titleKey: 'workspace.catalog.knowledgeOverviewTitle',
    })
    // v0.8.130 — the tip advertised the Context lens, which is no longer mounted. The
    // version stays 2 so people who already dismissed the tip are not shown it again.
    expect(GUIDED_TIPS.find(tip => tip.id === 'search-overview')).toMatchObject({
      version: 2,
      titleKey: 'workspace.catalog.searchOverviewTitle',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'studio-overview')).toMatchObject({
      version: 2,
      titleKey: 'workspace.catalog.studioOverviewTitle',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'podcasts-overview')).toMatchObject({
      version: 2,
      titleKey: 'workspace.catalog.podcastsOverviewTitle',
    })
    expect(GUIDED_TIPS.filter(tip => tip.version === 2)).toHaveLength(5)
  })

  it('uses path boundaries and chooses the most specific route', () => {
    expect(getGuidedTipForPath('/settings/api-keys')?.id).toBe('models-overview')
    expect(getGuidedTipForPath('/settings')?.id).toBe('settings-overview')
    expect(getGuidedTipForPath('/sources/example')?.id).toBe('sources-overview')
    expect(getGuidedTipForPath('/source-code')).toBeUndefined()
  })
})
