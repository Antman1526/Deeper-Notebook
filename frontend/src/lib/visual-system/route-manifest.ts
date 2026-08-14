export type VisualRoutePhase = 1 | 2 | 3 | 4

export type VisualRouteState =
  | 'loading'
  | 'empty'
  | 'populated'
  | 'processing'
  | 'degraded'
  | 'offline'
  | 'error'
  | 'unavailable'

export interface VisualRouteEntry {
  source: string
  route: string
  browserPath: string
  phase: VisualRoutePhase
  states: readonly VisualRouteState[]
}

export const VISUAL_ROUTE_MANIFEST = [
  {
    source: 'src/app/(auth)/login/page.tsx',
    route: '/login',
    browserPath: '/login',
    phase: 1,
    states: ['empty', 'error'],
  },
  {
    source: 'src/app/(dashboard)/page.tsx',
    route: '/',
    browserPath: '/',
    phase: 1,
    states: ['loading', 'empty', 'populated', 'degraded', 'offline'],
  },
  {
    source: 'src/app/(dashboard)/setup-wizard/page.tsx',
    route: '/setup-wizard',
    browserPath: '/setup-wizard',
    phase: 1,
    states: ['loading', 'populated', 'degraded', 'error'],
  },
  {
    source: 'src/app/(dashboard)/notebooks/page.tsx',
    route: '/notebooks',
    browserPath: '/notebooks',
    phase: 2,
    states: ['loading', 'empty', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/notebooks/[id]/page.tsx',
    route: '/notebooks/[id]',
    browserPath: '/notebooks/notebook-fixture-001',
    phase: 2,
    states: ['loading', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/sources/page.tsx',
    route: '/sources',
    browserPath: '/sources',
    phase: 2,
    states: ['loading', 'empty', 'populated', 'processing', 'error'],
  },
  {
    source: 'src/app/(dashboard)/sources/[id]/page.tsx',
    route: '/sources/[id]',
    browserPath: '/sources/source-fixture-001',
    phase: 2,
    states: ['loading', 'populated', 'processing', 'error'],
  },
  {
    source: 'src/app/(dashboard)/knowledge/page.tsx',
    route: '/knowledge',
    browserPath: '/knowledge',
    phase: 2,
    states: ['loading', 'empty', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/search/page.tsx',
    route: '/search',
    browserPath: '/search',
    phase: 2,
    states: ['empty', 'populated', 'processing', 'error'],
  },
  {
    source: 'src/app/(dashboard)/capture/page.tsx',
    route: '/capture',
    browserPath: '/capture',
    phase: 2,
    states: ['empty', 'processing', 'error'],
  },
  {
    source: 'src/app/(dashboard)/studio/page.tsx',
    route: '/studio',
    browserPath: '/studio',
    phase: 3,
    states: ['empty', 'processing', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/podcasts/page.tsx',
    route: '/podcasts',
    browserPath: '/podcasts',
    phase: 3,
    states: ['loading', 'empty', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/podcasts/studio/page.tsx',
    route: '/podcasts/studio',
    browserPath: '/podcasts/studio',
    phase: 3,
    states: ['empty', 'processing', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/study/page.tsx',
    route: '/study',
    browserPath: '/study',
    phase: 3,
    states: ['loading', 'empty', 'populated', 'degraded', 'offline', 'error'],
  },
  {
    source: 'src/app/(dashboard)/study/plans/[planId]/page.tsx',
    route: '/study/plans/[planId]',
    browserPath: '/study/plans/study_plan%3Afixture',
    phase: 3,
    states: ['loading', 'populated', 'processing', 'degraded', 'error'],
  },
  {
    source: 'src/app/(dashboard)/transformations/page.tsx',
    route: '/transformations',
    browserPath: '/transformations',
    phase: 3,
    states: ['loading', 'empty', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/settings/page.tsx',
    route: '/settings',
    browserPath: '/settings',
    phase: 4,
    states: ['populated'],
  },
  {
    source: 'src/app/(dashboard)/settings/api-keys/page.tsx',
    route: '/settings/api-keys',
    browserPath: '/settings/api-keys',
    phase: 4,
    states: ['loading', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/settings/launcher-prefs/page.tsx',
    route: '/settings/launcher-prefs',
    browserPath: '/settings/launcher-prefs',
    phase: 4,
    states: ['loading', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/settings/local-models/page.tsx',
    route: '/settings/local-models',
    browserPath: '/settings/local-models',
    phase: 4,
    states: ['loading', 'empty', 'populated', 'degraded', 'error'],
  },
  {
    source: 'src/app/(dashboard)/settings/mcp/page.tsx',
    route: '/settings/mcp',
    browserPath: '/settings/mcp',
    phase: 4,
    states: ['loading', 'empty', 'populated', 'error'],
  },
  {
    source: 'src/app/(dashboard)/advanced/page.tsx',
    route: '/advanced',
    browserPath: '/advanced',
    phase: 4,
    states: ['populated', 'unavailable'],
  },
] as const satisfies readonly VisualRouteEntry[]
