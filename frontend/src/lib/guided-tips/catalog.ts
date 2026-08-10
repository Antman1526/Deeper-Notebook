export interface GuidedTipDefinition {
  id: string
  version: number
  pathPrefix: string
  anchor: string
  title: string
  body: string
}

export const GUIDED_TIPS = [
  { id: 'dashboard-overview', version: 2, pathPrefix: '/', anchor: '/', title: 'Instrument Dock', body: 'Use the Instrument Dock to orient yourself, create a source, notebook, or podcast, and reach the tools that stay close at hand.' },
  { id: 'sources-overview', version: 1, pathPrefix: '/sources', anchor: '/sources', title: 'Sources', body: 'Add and organize the material Deeper Notebook can cite in answers and outputs.' },
  { id: 'capture-overview', version: 1, pathPrefix: '/capture', anchor: '/capture', title: 'Capture', body: 'Collect a quick idea or reference now, then organize it when you are ready.' },
  { id: 'notebooks-overview', version: 1, pathPrefix: '/notebooks', anchor: '/notebooks', title: 'Notebooks', body: 'Group sources, notes, grounded conversations, and generated research artifacts by project.' },
  { id: 'knowledge-overview', version: 2, pathPrefix: '/knowledge', anchor: '/knowledge', title: 'Notebook Index', body: 'Use the Notebook Index to move between notes, backlinks, graphs, searches, and read-only external vaults without losing your place.' },
  { id: 'search-overview', version: 2, pathPrefix: '/search', anchor: '/search', title: 'Context Lens', body: 'Keep trusted sources, grounded answers, and citations in view with the Context Lens while you explore.' },
  { id: 'studio-overview', version: 2, pathPrefix: '/studio', anchor: '/studio', title: 'Evidence Inserts', body: 'Read each Evidence Insert for its provider, freshness, retrieval time, and fingerprint before you review an output.' },
  { id: 'podcasts-overview', version: 2, pathPrefix: '/podcasts', anchor: '/podcasts', title: 'Podcast production review', body: 'Review the research set, outline, route, and citations before explicitly confirming optional podcast production.' },
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
