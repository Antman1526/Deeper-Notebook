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
    expect(GUIDED_TIPS.find(tip => tip.id === 'dashboard-overview')).toMatchObject({
      version: 2,
      title: 'Instrument Dock',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'knowledge-overview')).toMatchObject({
      version: 2,
      title: 'Notebook Index',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'search-overview')).toMatchObject({
      version: 2,
      title: 'Context Lens',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'studio-overview')).toMatchObject({
      version: 2,
      title: 'Evidence Inserts',
    })
    expect(GUIDED_TIPS.find(tip => tip.id === 'podcasts-overview')).toMatchObject({
      version: 2,
      title: 'Podcast production review',
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
