export interface GuidedTipDefinition {
  id: string
  version: number
  pathPrefix: string
  anchor: string
  title: string
  body: string
}

export const GUIDED_TIPS = [
  { id: 'dashboard-overview', version: 1, pathPrefix: '/', anchor: '/', title: 'Your research home', body: 'Resume recent work, create a notebook, or check active research and podcast production.' },
  { id: 'sources-overview', version: 1, pathPrefix: '/sources', anchor: '/sources', title: 'Sources', body: 'Add and organize the material Deeper Notebook can cite in answers and outputs.' },
  { id: 'capture-overview', version: 1, pathPrefix: '/capture', anchor: '/capture', title: 'Capture', body: 'Collect a quick idea or reference now, then organize it when you are ready.' },
  { id: 'notebooks-overview', version: 1, pathPrefix: '/notebooks', anchor: '/notebooks', title: 'Notebooks', body: 'Group sources, notes, grounded conversations, and generated research artifacts by project.' },
  { id: 'knowledge-overview', version: 1, pathPrefix: '/knowledge', anchor: '/knowledge', title: 'Knowledge workspace', body: 'Explore notes, backlinks, graphs, searches, and read-only external vaults in one persistent workspace.' },
  { id: 'search-overview', version: 1, pathPrefix: '/search', anchor: '/search', title: 'Ask and Search', body: 'Choose the sources you trust, ask a grounded question, and open citations in context.' },
  { id: 'studio-overview', version: 1, pathPrefix: '/studio', anchor: '/studio', title: 'Studio', body: 'Turn selected research into a controlled output. Opening Studio never starts generation.' },
  { id: 'podcasts-overview', version: 1, pathPrefix: '/podcasts', anchor: '/podcasts', title: 'Podcasts', body: 'Create optional source-grounded audio, review its outline, and inspect the transcript and citations.' },
  { id: 'study-overview', version: 1, pathPrefix: '/study', anchor: '/study', title: 'Study', body: 'Build focused review material from selected notebook sources.' },
  { id: 'models-overview', version: 1, pathPrefix: '/settings/api-keys', anchor: '/settings/api-keys', title: 'Models', body: 'Choose local or connected models by role and verify readiness before using them.' },
  { id: 'settings-overview', version: 1, pathPrefix: '/settings', anchor: '/settings', title: 'Settings', body: 'Control appearance, guided tips, providers, privacy, and advanced application behavior.' },
] as const satisfies readonly GuidedTipDefinition[]

export function getGuidedTipForPath(pathname: string): GuidedTipDefinition | undefined {
  return [...GUIDED_TIPS]
    .filter(tip => tip.pathPrefix === '/'
      ? pathname === '/'
      : pathname === tip.pathPrefix || pathname.startsWith(`${tip.pathPrefix}/`))
    .sort((a, b) => b.pathPrefix.length - a.pathPrefix.length)[0]
}
