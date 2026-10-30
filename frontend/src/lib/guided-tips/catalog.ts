export interface GuidedTipDefinition {
  id: string
  version: number
  pathPrefix: string
  anchor: string
  /** i18n keys; the English copy lives in the locale files. */
  titleKey: string
  bodyKey: string
}

export const GUIDED_TIPS = [
  { id: 'dashboard-overview', version: 2, pathPrefix: '/', anchor: '/', titleKey: 'workspace.catalog.dashboardOverviewTitle', bodyKey: 'workspace.catalog.dashboardOverviewBody' },
  { id: 'sources-overview', version: 1, pathPrefix: '/sources', anchor: '/sources', titleKey: 'workspace.catalog.sourcesOverviewTitle', bodyKey: 'workspace.catalog.sourcesOverviewBody' },
  { id: 'capture-overview', version: 1, pathPrefix: '/capture', anchor: '/capture', titleKey: 'workspace.catalog.captureOverviewTitle', bodyKey: 'workspace.catalog.captureOverviewBody' },
  { id: 'notebooks-overview', version: 1, pathPrefix: '/notebooks', anchor: '/notebooks', titleKey: 'workspace.catalog.notebooksOverviewTitle', bodyKey: 'workspace.catalog.notebooksOverviewBody' },
  { id: 'knowledge-overview', version: 2, pathPrefix: '/knowledge', anchor: '/knowledge', titleKey: 'workspace.catalog.knowledgeOverviewTitle', bodyKey: 'workspace.catalog.knowledgeOverviewBody' },
  { id: 'search-overview', version: 2, pathPrefix: '/search', anchor: '/search', titleKey: 'workspace.catalog.searchOverviewTitle', bodyKey: 'workspace.catalog.searchOverviewBody' },
  { id: 'studio-overview', version: 2, pathPrefix: '/studio', anchor: '/studio', titleKey: 'workspace.catalog.studioOverviewTitle', bodyKey: 'workspace.catalog.studioOverviewBody' },
  { id: 'podcasts-overview', version: 2, pathPrefix: '/podcasts', anchor: '/podcasts', titleKey: 'workspace.catalog.podcastsOverviewTitle', bodyKey: 'workspace.catalog.podcastsOverviewBody' },
  { id: 'study-overview', version: 1, pathPrefix: '/study', anchor: '/study', titleKey: 'workspace.catalog.studyOverviewTitle', bodyKey: 'workspace.catalog.studyOverviewBody' },
  { id: 'models-overview', version: 1, pathPrefix: '/settings/api-keys', anchor: '/settings/api-keys', titleKey: 'workspace.catalog.modelsOverviewTitle', bodyKey: 'workspace.catalog.modelsOverviewBody' },
  { id: 'settings-overview', version: 1, pathPrefix: '/settings', anchor: '/settings', titleKey: 'workspace.catalog.settingsOverviewTitle', bodyKey: 'workspace.catalog.settingsOverviewBody' },
] as const satisfies readonly GuidedTipDefinition[]

export function getGuidedTipForPath(pathname: string): GuidedTipDefinition | undefined {
  return [...GUIDED_TIPS]
    .filter(tip => tip.pathPrefix === '/'
      ? pathname === '/'
      : pathname === tip.pathPrefix || pathname.startsWith(`${tip.pathPrefix}/`))
    .sort((a, b) => b.pathPrefix.length - a.pathPrefix.length)[0]
}
