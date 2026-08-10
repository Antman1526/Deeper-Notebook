import { describe, expect, it } from 'vitest'

import { systemRouteFolioMetadata } from './SystemRouteFrames'

describe('system route folio mapping', () => {
  it.each([
    ['/podcasts', 'Podcasts'],
    ['/transformations', 'Transformations'],
    ['/settings', 'Settings'],
    ['/settings/api-keys', 'API keys'],
    ['/settings/local-models', 'Local models'],
    ['/settings/mcp', 'Integrations'],
    ['/settings/launcher-prefs', 'Launcher preferences'],
    ['/advanced', 'Advanced tools'],
    ['/setup-wizard', 'Setup'],
  ] as const)('maps %s to the %s folio', (route, title) => {
    expect(systemRouteFolioMetadata[route]).toMatchObject({ title })
  })
})
