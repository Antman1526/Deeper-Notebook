import { describe, expect, it } from 'vitest'

import { systemRouteFolioMetadata } from './SystemRouteFrames'

describe('system route folio mapping', () => {
  it.each([
    ['/podcasts', 'workspace.systemRouteFrames.titlePodcasts'],
    ['/transformations', 'workspace.systemRouteFrames.titleTransformations'],
    ['/settings', 'workspace.systemRouteFrames.titleSettings'],
    ['/settings/api-keys', 'workspace.systemRouteFrames.titleApiKeys'],
    ['/settings/local-models', 'workspace.systemRouteFrames.titleLocalModels'],
    ['/settings/mcp', 'workspace.systemRouteFrames.titleIntegrations'],
    ['/settings/launcher-prefs', 'workspace.systemRouteFrames.titleLauncherPreferences'],
    ['/advanced', 'workspace.systemRouteFrames.titleAdvancedTools'],
    ['/setup-wizard', 'workspace.systemRouteFrames.titleSetup'],
  ] as const)('maps %s to the %s folio', (route, titleKey) => {
    expect(systemRouteFolioMetadata[route]).toMatchObject({ titleKey })
  })
})
