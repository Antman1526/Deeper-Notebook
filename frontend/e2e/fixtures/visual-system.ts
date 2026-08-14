import type { Page, Request } from '@playwright/test'

import { installLuminousFolioFixture } from './luminous-folio'
import {
  canonicalStudyApiPath,
  installStudyWorkbenchFixture,
  studyWorkbenchFixtures,
  type StudyRequestLedger,
} from './study-workbench'
import { researchWorkbenchFixtures } from './research-workbench'
import type { ThemeId } from '@/lib/themes/catalog'

export const VISUAL_MATRIX_THEMES = [
  'gemini-forward-light',
  'research-core-dark',
  'high-contrast-light',
] as const satisfies readonly ThemeId[]

export const VISUAL_MATRIX_VIEWPORTS = [
  { name: 'mobile', width: 320, height: 844 },
  { name: 'narrow', width: 768, height: 1024 },
  { name: 'compact-desktop', width: 1020, height: 631 },
  { name: 'large-desktop', width: 1440, height: 900 },
] as const

export type VisualMatrixTheme = typeof VISUAL_MATRIX_THEMES[number]
export type VisualMatrixViewport = typeof VISUAL_MATRIX_VIEWPORTS[number]

export interface VisualRequestReceipt {
  viewport: string
  method: string
  canonicalPath: string
  status: number
}

export interface VisualRequestLedger {
  expected: Record<string, number>
  seen: Record<string, number>
  expectedByViewport: Record<string, Record<string, number>>
  seenByViewport: Record<string, Record<string, number>>
  receipts: VisualRequestReceipt[]
  unexpected: string[]
  external: string[]
}

export type VisualRequestFrequencyMap = Readonly<Record<string, number>>

/**
 * The route-owned request contract is deliberately explicit. It is not
 * derived from the requests observed by a cell: a route that adds, removes,
 * or duplicates a call must make that change visible here first.
 */
export const VISUAL_ROUTE_EXPECTED_REQUESTS: Readonly<Record<string, VisualRequestFrequencyMap>> = {
  '/login': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 2,
  },
  '/': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/notebooks': 2,
    'GET /api/runtime/snapshot': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/setup-wizard': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/notebooks': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/notebooks': 3,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/notebooks/[id]': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/notebooks/notebook-fixture-001': 1,
    'GET /api/sources': 1,
    'GET /api/notes': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
    'GET /api/studio/notebooks/notebook-fixture-001/artifacts': 1,
    'GET /api/models': 1,
    'GET /api/models/defaults': 1,
    'GET /api/mcp': 1,
    'GET /api/mcp/web-search': 1,
    'GET /api/chat/sessions': 1,
    'GET /api/notebooks/notebook-fixture-001/suggested-questions': 1,
    'POST /api/chat/context': 1,
  },
  '/sources': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/sources': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/sources/[id]': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/sources/source-fixture-001': 1,
    'GET /api/sources/source-fixture-001/insights': 1,
    'GET /api/transformations': 2,
    'GET /api/models': 1,
    'GET /api/models/defaults': 1,
    'GET /api/mcp': 1,
    'GET /api/mcp/web-search': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/sources/source-fixture-001/chat/sessions': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/knowledge': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/deeper-notebook/workspace/knowledge': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/deeper-notebook/knowledge/bookmarks': 1,
    'GET /api/deeper-notebook/knowledge/bookmark-folders': 1,
    'GET /api/deeper-notebook/knowledge/workspaces': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/notebooks': 2,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/search': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/models/defaults': 1,
    'GET /api/models': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/capture': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/capture/roots': 1,
    'GET /api/capture/items': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/studio': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/podcasts': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/notebooks': 2,
    'GET /api/episode-profiles': 1,
    'GET /api/podcasts/episodes': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/speaker-profiles': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/healthz/deep': 1,
  },
  '/podcasts/studio': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/study': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/study/plans': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/study/cards/due': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/study/plans/[planId]': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/study/plans/study_plan:fixture': 1,
    'GET /api/study/plans/study_plan:fixture/syllabus': 1,
    'GET /api/study/plans/study_plan:fixture/sources/readiness': 1,
    'GET /api/study/plans/study_plan:fixture/progress': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/credentials/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/transformations': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/transformations/default-prompt': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/transformations': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/settings': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/settings': 1,
    'GET /api/updates/check': 1,
    'GET /api/settings/observability': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/system/network-status': 1,
    'GET /api/runtime/snapshot': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/settings/api-keys': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 2,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/credentials': 1,
    'GET /api/models': 1,
    'GET /api/models/defaults': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
    'POST /api/credentials/detect-osaurus': 1,
  },
  '/settings/launcher-prefs': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/launcher-prefs': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/settings/local-models': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/local-models/recommendations': 1,
    'GET /api/local-models/downloads': 1,
    'GET /api/local-models/inventory': 1,
    'GET /api/local-models/settings': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
    'POST /api/local-models/route-plan': 2,
  },
  '/settings/mcp': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/mcp': 1,
    'GET /api/mcp/recommendations': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
  '/advanced': {
    'GET /config': 2,
    'GET /api/config': 2,
    'GET /api/auth/status': 1,
    'GET /api/deeper-notebook/gmail/status': 1,
    'GET /api/local-models/health': 1,
    'GET /api/credentials/status': 1,
    'GET /api/credentials/env-status': 1,
    'GET /api/system/db-repair-needed': 1,
    'GET /api/updates/check': 1,
    'GET /api/system/network-status': 1,
    'GET /api/deeper-notebook/vaults': 1,
    'GET /api/notebooks': 2,
    'GET /api/deeper-notebook/overlay/notes': 1,
    'GET /api/transformations': 1,
    'GET /api/settings': 1,
    'GET /api/episode-profiles': 1,
    'GET /api/healthz/deep': 1,
  },
}

/**
 * Cell maps are keyed independently even when they currently share a route
 * map. This keeps theme/viewport-specific request drift observable without
 * letting the fixture infer expectations from a cell's own traffic.
 */
export const VISUAL_CELL_EXPECTED_REQUESTS: Readonly<Record<string, VisualRequestFrequencyMap>> = Object.freeze(
  Object.fromEntries(
    Object.entries(VISUAL_ROUTE_EXPECTED_REQUESTS).flatMap(([route, expected]) => (
      VISUAL_MATRIX_THEMES.flatMap((theme) => (
        VISUAL_MATRIX_VIEWPORTS.map((viewport) => {
          const cellExpected = { ...expected }
          if (route === '/notebooks/[id]' && viewport.name === 'large-desktop') {
            cellExpected['GET /api/sources'] = 2
          }
          return [
            `${route}|${theme}|${viewport.name}`,
            cellExpected,
          ] as const
        })
      ))
    ))
  ) as Record<string, VisualRequestFrequencyMap>,
)

export interface VisualSystemFixtureOptions {
  theme: VisualMatrixTheme
  route?: string
  viewport?: VisualMatrixViewport
  ledger?: VisualRequestLedger
  unexpectedExternalRequests?: string[]
}

export interface VisualSystemFixtureHandle {
  ledger: VisualRequestLedger
  studyLedger: StudyRequestLedger
  expectedFrequency: Record<string, number>
  seenFrequency: Record<string, number>
  studySeenFrequency: Record<string, number>
}

export function visualCellKey(
  route: string,
  theme: VisualMatrixTheme,
  viewport: VisualMatrixViewport,
): string {
  return `${route}|${theme}|${viewport.name}`
}

export function expectedVisualRequestFrequency(
  route: string,
  theme: VisualMatrixTheme,
  viewport: VisualMatrixViewport,
): VisualRequestFrequencyMap {
  const key = visualCellKey(route, theme, viewport)
  const expected = VISUAL_CELL_EXPECTED_REQUESTS[key]
  if (!expected || !VISUAL_ROUTE_EXPECTED_REQUESTS[route]) {
    throw new Error(`No exact expected request-frequency map for cell ${key}`)
  }
  return expected
}

export function frequencyMapFromLabels(labels: readonly string[]): Record<string, number> {
  return labels.reduce<Record<string, number>>((frequency, label) => {
    frequency[label] = (frequency[label] ?? 0) + 1
    return frequency
  }, {})
}

const notebook = researchWorkbenchFixtures.notebook
const source = researchWorkbenchFixtures.source
const sourceList = {
  id: source.id,
  title: source.title,
  topics: [],
  provenance: { origin: 'browser fixture' },
  source_type: source.source_type,
  notebook_count: 1,
  is_shared: false,
  asset: null,
  embedded: false,
  embedded_chunks: 0,
  insights_count: 0,
  created: source.created_at,
  updated: source.created_at,
  file_available: true,
  extracted_char_count: source.content.length,
  extraction_quality: 'ok',
  status: 'completed',
} as const
const sourceDetail = {
  ...sourceList,
  full_text: source.content,
  notebooks: [notebook.id],
} as const

const health = {
  status: 'healthy',
  checks: {
    database: { status: 'ready', ok: true, error: null },
    migrations: { status: 'ready', ok: true, error: null },
    embedding_model: { status: 'ready', ok: true, error: null },
    chat_model: { status: 'ready', ok: true, error: null },
    command_registry: { status: 'ready', ok: true, error: null },
  },
} as const

const setupNotReadyHealth = {
  status: 'not_ready',
  checks: {
    database: { status: 'offline', ok: false, error: 'Fixture setup gate' },
    migrations: { status: 'error', ok: false, error: 'Fixture setup gate' },
    embedding_model: { status: 'missing', ok: false, error: 'Fixture setup gate' },
    chat_model: { status: 'missing', ok: false, error: 'Fixture setup gate' },
    command_registry: { status: 'error', ok: false, error: 'Fixture setup gate' },
  },
} as const

const runtimeSnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'ready',
  reasons: [],
  readiness: { state: 'ready', database: 'online', migrations: 'applied' },
  startup: { state: 'ready', stages: [] },
  updates: { state: 'ready', enabled: false, update_available: false, current_version: 'fixture' },
  vault: { state: 'ready', ready: 0, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready', projected: 0, unchanged: 0, failed: 0 },
  backup: { state: 'ready', file_count: 0, newest_age_seconds: 0 },
} as const

function emptyLedger(): VisualRequestLedger {
  return {
    expected: {},
    seen: {},
    expectedByViewport: {},
    seenByViewport: {},
    receipts: [],
    unexpected: [],
    external: [],
  }
}

function viewportName(page: Page): string {
  const width = page.viewportSize()?.width
  return VISUAL_MATRIX_VIEWPORTS.find((viewport) => viewport.width === width)?.name ?? String(width ?? 'unknown')
}

function requestLabel(method: string, pathname: string): string {
  return `${method} ${pathname}`
}

function increment(map: Record<string, number>, key: string): void {
  map[key] = (map[key] ?? 0) + 1
}

function isPageOrigin(url: string): boolean {
  try {
    const configuredPort = process.env.PLAYWRIGHT_PORT ?? '3117'
    const configuredOrigin = process.env.PLAYWRIGHT_BASE_URL
      ? new URL(process.env.PLAYWRIGHT_BASE_URL).origin
      : `http://127.0.0.1:${configuredPort}`
    return new URL(url).origin === configuredOrigin
  } catch {
    return false
  }
}

function recordReceipt(
  page: Page,
  ledger: VisualRequestLedger,
  method: string,
  pathname: string,
  status: number,
): string {
  const canonicalPath = canonicalStudyApiPath(pathname)
  const label = requestLabel(method, canonicalPath)
  const viewport = viewportName(page)
  increment(ledger.seen, label)
  ledger.seenByViewport[viewport] ??= {}
  increment(ledger.seenByViewport[viewport], label)
  ledger.receipts.push({ viewport, method, canonicalPath, status })
  return label
}

function isExternalUrl(url: string): boolean {
  return !isPageOrigin(url)
}

function sameOriginApiPath(url: string): string | null {
  try {
    const parsed = new URL(url)
    if (!isPageOrigin(url) || !parsed.pathname.startsWith('/api/')) return null
    return canonicalStudyApiPath(parsed.pathname)
  } catch {
    return null
  }
}

function jsonBody(pathname: string, page: Page): unknown {
  if (pathname === '/config') return { apiUrl: '' }
  if (pathname === '/api/config') return { version: 'fixture', latestVersion: null, hasUpdate: false, dbStatus: 'healthy' }
  // Keep /login as a real login surface while allowing dashboard routes to
  // render their own route content in the same deterministic browser matrix.
  if (pathname === '/api/auth/status') {
    return page.url().includes('/login')
      ? { auth_enabled: true, auth_required: true }
      : { auth_enabled: false, auth_required: false }
  }
  if (pathname === '/api/version') return { version: 'fixture' }
  if (pathname === '/api/readyz') return { status: 'ready', checks: { database: 'online', database_error: null, migrations_applied: true, migrations_pending: false, migrations_error: null } }
  if (pathname === '/healthz/deep' || pathname === '/api/healthz/deep') {
    return page.url().includes('/setup-wizard') ? setupNotReadyHealth : health
  }
  if (pathname === '/api/runtime/snapshot') return runtimeSnapshot
  if (pathname === '/api/local-models/health') return { overall: 'healthy', models: [] }
  if (pathname === '/api/system/db-repair-needed') return { needs_repair: false }
  if (pathname === '/api/updates/check') return { current: 'fixture', latest: null, update_available: false, skipped: false, skipped_version: null, html_url: null, published_at: null, enabled: false, last_check: null }
  if (pathname === '/api/system/network-status') return { status: 'online', forced_offline: false, local_fallback_model: null, checked_epoch_ms: 0 }
  if (pathname === '/api/notebooks') return page.url().includes('/setup-wizard') ? [] : [notebook]
  if (pathname === '/api/notebooks/notebook-fixture-001') return notebook
  if (pathname === '/api/notebooks/notebook-fixture-001/suggested-questions') return { questions: [] }
  if (pathname === '/api/sources') return [sourceList]
  if (pathname === '/api/sources/source-fixture-001') return sourceDetail
  if (pathname === '/api/sources/source-fixture-001/insights') return []
  if (pathname === '/api/sources/source-fixture-001/chat/sessions') return []
  if (pathname === '/api/notes') return []
  if (pathname === '/api/chat/sessions') return []
  if (pathname === '/api/studio/notebooks/notebook-fixture-001/artifacts') return []
  if (pathname === '/api/deeper-notebook/gmail/status') return { connected: false, configured: false }
  if (pathname === '/api/deeper-notebook/vaults') return []
  if (pathname === '/api/deeper-notebook/overlay/notes') return []
  if (pathname === '/api/deeper-notebook/workspace/knowledge') return {
    version: 1,
    active_pane_id: 'pane-1',
    next_id: 1,
    panes: {
      'pane-1': { id: 'pane-1', active_tab_id: null, tabs: [] },
    },
    layout: { type: 'pane', pane_id: 'pane-1' },
    navigation: {
      utility_mode: 'sources',
      sidebar_visible: true,
      sidebar_width: 320,
      active_bookmark_folder_id: null,
      bookmark_tags: [],
      source_tree_query: '',
      search_query: '',
      search_mode: 'text',
      active_draft_id: null,
      selected_space_ids: [],
      authority_filters: [],
      metrics_visible: true,
    },
  }
  if (pathname === '/api/deeper-notebook/knowledge/bookmarks') return { items: [], next_cursor: null }
  if (pathname === '/api/deeper-notebook/knowledge/bookmark-folders') return { items: [] }
  if (pathname === '/api/deeper-notebook/knowledge/workspaces') return { items: [] }
  if (pathname === '/api/settings') return { configured: {}, source: {}, encryption_configured: true }
  if (pathname === '/api/settings/observability') return { enabled: false }
  if (pathname === '/api/launcher-prefs') return { prefs: {} }
  if (pathname === '/api/mcp') return []
  if (pathname === '/api/mcp/recommendations') return { recommendations: [] }
  if (pathname === '/api/mcp/web-search') return { enabled: false, provider: null, tool_name: 'web_search' }
  if (pathname === '/api/credentials') return []
  if (pathname === '/api/credentials/status') return { configured: {}, source: {}, encryption_configured: true }
  if (pathname === '/api/credentials/env-status') return {}
  if (pathname === '/api/credentials/detect-osaurus') return { running: false, port: 1337, models_registered: 0, credential_id: null, detail: 'not running' }
  if (pathname === '/api/models') return []
  if (pathname === '/api/models/defaults') return {}
  if (pathname === '/api/episode-profiles' || pathname === '/api/speaker-profiles') return []
  if (pathname === '/api/podcasts/episodes') return []
  if (pathname === '/api/transformations') return []
  if (pathname === '/api/transformations/default-prompt') return { prompt: '' }
  if (pathname === '/api/capture/roots' || pathname === '/api/capture/items') return []
  if (pathname === '/api/local-models/inventory') return { model_dir: 'redacted', available: false, models: [] }
  if (pathname === '/api/local-models/settings') return {
    model_dir: 'redacted', execution_policy: 'strict_local', compute_profile: 'balanced',
    local_model_memory_limit_bytes: null, role_overrides: {}, trusted_external_model_roots: [],
  }
  if (pathname === '/api/local-models/recommendations' || pathname === '/api/local-models/downloads') return { recommendations: [], downloads: [] }
  if (pathname === '/api/local-models/route-plan') return {
    role: 'fixture', outcome: 'blocked', selected_model_id: null, selected_provider: null,
    resource_tier: null, selection_source: null, route_reason: 'No local model is configured in the visual fixture.',
    escalation_model_ids: [], blocked_reason: 'No local model is configured in the visual fixture.',
    selected_fingerprint: null, selected_measurements: {},
  }
  if (pathname === '/api/study/plans') return [studyWorkbenchFixtures.plan]
  if (pathname === '/api/study/cards/due') return studyWorkbenchFixtures.cards
  if (pathname === '/api/study/plans/study_plan:fixture') return studyWorkbenchFixtures.plan
  if (pathname === '/api/study/plans/study_plan:fixture/syllabus') return studyWorkbenchFixtures.syllabus
  if (pathname === '/api/study/plans/study_plan:fixture/sources/readiness') return studyWorkbenchFixtures.readiness
  if (pathname === '/api/study/plans/study_plan:fixture/progress') return studyWorkbenchFixtures.progress
  return {}
}

function registerJsonRoute(
  page: Page,
  ledger: VisualRequestLedger,
  pathname: string,
  body: unknown | ((page: Page) => unknown),
  method = 'GET',
): void {
  const canonical = canonicalStudyApiPath(pathname)
  page.route((url) => isPageOrigin(url.href) && canonicalStudyApiPath(url.pathname) === canonical, async (route) => {
    const requestMethod = route.request().method()
    const status = requestMethod === method ? 200 : 405
    const label = recordReceipt(page, ledger, requestMethod, canonical, status)
    if (requestMethod !== method) ledger.unexpected.push(label)
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(requestMethod === method
        ? typeof body === 'function' ? body(page) : body
        : { detail: 'method not allowed' }),
    })
  })
}

const COMMON_GET_ROUTES = [
  '/config', '/api/config', '/api/auth/status', '/api/version', '/api/readyz',
  '/healthz/deep', '/api/healthz/deep', '/api/runtime/snapshot', '/api/local-models/health',
  '/api/system/db-repair-needed', '/api/updates/check', '/api/system/network-status',
  '/api/notebooks', '/api/notebooks/notebook-fixture-001', '/api/notebooks/notebook-fixture-001/suggested-questions',
  '/api/sources', '/api/sources/source-fixture-001', '/api/sources/source-fixture-001/insights',
  '/api/sources/source-fixture-001/chat/sessions', '/api/notes', '/api/chat/sessions',
  '/api/studio/notebooks/notebook-fixture-001/artifacts', '/api/deeper-notebook/gmail/status',
  '/api/deeper-notebook/vaults', '/api/deeper-notebook/overlay/notes',
  '/api/deeper-notebook/knowledge/bookmarks', '/api/deeper-notebook/knowledge/bookmark-folders',
  '/api/deeper-notebook/knowledge/workspaces', '/api/settings', '/api/settings/observability',
  '/api/launcher-prefs', '/api/mcp', '/api/mcp/recommendations', '/api/mcp/web-search',
  '/api/credentials', '/api/credentials/status', '/api/credentials/env-status',
  '/api/models', '/api/models/defaults', '/api/episode-profiles', '/api/speaker-profiles',
  '/api/podcasts/episodes', '/api/transformations', '/api/transformations/default-prompt',
  '/api/capture/roots', '/api/capture/items', '/api/local-models/inventory', '/api/local-models/settings',
  '/api/local-models/recommendations', '/api/local-models/downloads',
  '/api/study/plans', '/api/study/cards/due', '/api/study/plans/study_plan:fixture',
  '/api/study/plans/study_plan:fixture/syllabus', '/api/study/plans/study_plan:fixture/sources/readiness',
  '/api/study/plans/study_plan:fixture/progress',
] as const

export async function installVisualSystemFixture(
  page: Page,
  {
    theme,
    route,
    viewport,
    ledger = emptyLedger(),
    unexpectedExternalRequests = [],
  }: VisualSystemFixtureOptions,
): Promise<VisualSystemFixtureHandle> {
  const studyLedger: StudyRequestLedger = { expected: [], seen: [], unexpected: [] }

  const expected = route && viewport
    ? expectedVisualRequestFrequency(route, theme, viewport)
    : {}
  ledger.expected = { ...expected }
  ledger.expectedByViewport = viewport ? { [viewport.name]: { ...expected } } : {}
  studyLedger.expected = Object.entries(expected).flatMap(([label, count]) => (
    label.includes(' /api/study/') ? Array.from({ length: count }, () => label) : []
  ))
  if (viewport) studyLedger.expectedByViewport = { [String(viewport.width)]: [...studyLedger.expected] }

  await page.addInitScript(() => {
    const state = { value: 0, supported: false }
    ;(window as Window & {
      __dnVisualSystemLayoutShift?: { value: number; supported: boolean }
    }).__dnVisualSystemLayoutShift = state
    if (typeof PerformanceObserver === 'undefined') return
    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number }
          if (!shift.hadRecentInput) state.value += shift.value ?? 0
        }
      })
      observer.observe({ type: 'layout-shift', buffered: true })
      state.supported = true
    } catch {
      state.supported = false
    }
  })

  // Unknown same-origin API traffic is recorded once at the request boundary
  // and aborted. The set is initialized before the guard so Playwright's
  // requestfailed event cannot create a duplicate receipt.
  const unknownRequests = new Set<Request>()
  const recordUnknown = (request: Request, status: number): void => {
    if (unknownRequests.has(request)) return
    unknownRequests.add(request)
    const pathname = sameOriginApiPath(request.url())
    if (!pathname) return
    const label = recordReceipt(page, ledger, request.method(), pathname, status)
    ledger.unexpected.push(status === 0 ? `${label} (failed)` : label)
  }

  // This guard runs before any exact fixture routes are installed. Playwright
  // resolves the newest matching route first, so named exact handlers below
  // win for known paths while an unrecognized same-origin API aborts before
  // reaching Next's proxy.
  await page.route((url) => isPageOrigin(url.href) && url.pathname.startsWith('/api/'), async (requestRoute) => {
    const request = requestRoute.request()
    recordUnknown(request, 0)
    await requestRoute.abort()
  })

  await installLuminousFolioFixture(page, { theme, unexpectedApiRequests: ledger.unexpected })
  await page.unroute('**/api/**')
  await installStudyWorkbenchFixture(page, { state: 'approved', ledger: studyLedger, unexpectedExternalRequests })
  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en-US')
  })

  page.on('response', (response) => {
    const pathname = sameOriginApiPath(response.url())
    if (!pathname) return
    const label = requestLabel(response.request().method(), pathname)
    if ((ledger.seen[label] ?? 0) > 0 || studyLedger.seen.includes(label)) return
    recordUnknown(response.request(), response.status())
  })
  page.on('requestfailed', (request) => {
    if (sameOriginApiPath(request.url())) recordUnknown(request, 0)
  })

  for (const pathname of COMMON_GET_ROUTES) {
    registerJsonRoute(page, ledger, pathname, (currentPage: Page) => jsonBody(pathname, currentPage))
  }

  const knowledgeWorkspacePath = '/api/deeper-notebook/workspace/knowledge'
  page.route((url) => (
    isPageOrigin(url.href)
    && canonicalStudyApiPath(url.pathname) === knowledgeWorkspacePath
  ), async (routeHandler) => {
    const request = routeHandler.request()
    const method = request.method()
    const supported = method === 'GET' || method === 'PUT'
    const status = supported ? 200 : 405
    const label = recordReceipt(page, ledger, method, knowledgeWorkspacePath, status)
    if (!supported) ledger.unexpected.push(label)
    const body = method === 'GET'
      ? jsonBody(knowledgeWorkspacePath, page)
      : method === 'PUT'
        ? request.postDataJSON()
        : { detail: 'method not allowed' }
    await routeHandler.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })

  registerJsonRoute(page, ledger, '/api/visual-system/method-probe', { ok: true })
  registerJsonRoute(page, ledger, '/api/chat/context', {}, 'POST')
  registerJsonRoute(page, ledger, '/api/credentials/detect-osaurus', jsonBody('/api/credentials/detect-osaurus', page), 'POST')
  registerJsonRoute(page, ledger, '/api/local-models/route-plan', jsonBody('/api/local-models/route-plan', page), 'POST')
  registerJsonRoute(page, ledger, '/api/study/plans/study_plan:fixture/progress:decision', { decision: 'accepted' }, 'POST')
  registerJsonRoute(page, ledger, '/api/study/plans/study_plan:fixture/assistants/source_guide:invoke', { status: 'completed' }, 'POST')
  registerJsonRoute(page, ledger, '/api/study/plans/study_plan:fixture/assistants/practice_coach:invoke', { status: 'completed' }, 'POST')
  registerJsonRoute(page, ledger, '/api/study/plans/study_plan:fixture/voice:capability', { stt: 'unavailable', tts: 'unavailable' })
  registerJsonRoute(page, ledger, '/api/study/plans/study_plan:fixture/voice:transcribe', { transcript: 'Fixture transcript.' }, 'POST')
  registerJsonRoute(page, ledger, '/api/study/plans/study_plan:fixture/voice:synthesize', { audio: 'fixture-audio' }, 'POST')

  // This guard is installed after every named route so an external request
  // cannot be captured by a path-only legacy fixture handler. The origin
  // check includes the exact configured port, not merely a loopback hostname.
  await page.route((url) => isExternalUrl(url.href), async (requestRoute) => {
    const url = requestRoute.request().url()
    ledger.external.push(url)
    unexpectedExternalRequests.push(url)
    await requestRoute.abort()
  })

  return {
    ledger,
    studyLedger,
    expectedFrequency: ledger.expected,
    seenFrequency: ledger.seen,
    studySeenFrequency: frequencyMapFromLabels(studyLedger.seen),
  }
}
