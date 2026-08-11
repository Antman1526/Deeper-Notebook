import type { Page, Route } from '@playwright/test'

import { THEME_CATALOG, isThemeId, type ThemeId } from '@/lib/themes/catalog'

export interface ThemeVisualFixture {
  unexpectedRequests: string[]
}

const settings = {
  default_content_processing_engine_doc: 'auto',
  default_content_processing_engine_url: 'auto',
  default_embedding_option: 'ask',
  auto_delete_files: 'no',
  offline_mode: false,
  auto_summarize_on_ingest: false,
  auto_extract_topics_on_ingest: false,
}

const observability = {
  slow_query_log_ms: null,
  encryption_kdf: 'argon2id',
  checkpoint_keep_per_thread: 10,
  checkpoint_prune_interval_hours: 24,
  db_pool_size: 8,
  db_pool_disabled: false,
  metrics_endpoint_path: '/metrics',
}

const updateStatus = {
  current: 'fixture',
  latest: null,
  update_available: false,
  skipped: false,
  skipped_version: null,
  html_url: null,
  published_at: null,
  enabled: false,
  last_check: null,
}

const runtimeSnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'degraded',
  reasons: ['auto_export_unknown', 'provenance_unknown'],
  readiness: { state: 'ready', database: 'online', migrations: 'applied' },
  startup: {
    state: 'ready',
    stages: [
      { stage: 'launcher_start', elapsed_ms: 2 },
      { stage: 'core_ready', elapsed_ms: 18 },
    ],
  },
  updates: { state: 'ready', enabled: false, update_available: false, current_version: 'fixture' },
  vault: { state: 'ready', ready: 0, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready', projected: 0, unchanged: 0, failed: 0 },
  backup: {
    state: 'unknown',
    freshness: 'unknown',
    integrity: 'unknown',
    file_count: 0,
    newest_age_seconds: null,
    newest_size_bytes: null,
    newest_timestamp: null,
  },
  provenance: {
    state: 'unknown',
    mount_count: 0,
    external_read_only_count: 0,
    source_fingerprint_state: 'unknown',
  },
}

function requestLabel(route: Route): string {
  const request = route.request()
  return `${request.method()} ${new URL(request.url()).pathname}`
}

async function fulfillJson(
  page: Page,
  pathname: string,
  body: unknown,
  unexpectedRequests: string[],
  allowedMethods: readonly string[] = ['GET', 'HEAD'],
): Promise<void> {
  await page.route((url) => url.pathname === pathname, async (route) => {
    if (!allowedMethods.includes(route.request().method())) {
      unexpectedRequests.push(requestLabel(route))
      await route.fulfill({
        status: 405,
        contentType: 'application/json',
        headers: { Allow: allowedMethods.join(', ') },
        body: JSON.stringify({ detail: 'Method not allowed by theme visual fixture' }),
      })
      return
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

export async function installThemeVisualFixture(
  page: Page,
  theme: ThemeId,
): Promise<ThemeVisualFixture> {
  const unexpectedRequests: string[] = []

  await page.context().addCookies([
    { name: 'wizard_completed', value: 'true', domain: '127.0.0.1', path: '/' },
    { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
  ])
  await page.addInitScript((themeId) => {
    localStorage.setItem('dn-theme', themeId)
  }, theme)

  await page.route('**/api/**', async (route) => {
    unexpectedRequests.push(requestLabel(route))
    await route.fulfill({
      status: 501,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unhandled API request in theme visual fixture' }),
    })
  })

  await fulfillJson(page, '/config', { apiUrl: '' }, unexpectedRequests)
  await fulfillJson(page, '/api/config', {
    version: 'fixture', latestVersion: null, hasUpdate: false, dbStatus: 'healthy',
  }, unexpectedRequests)
  await fulfillJson(page, '/api/auth/get-session', null, unexpectedRequests)
  await fulfillJson(page, '/api/auth/status', { auth_enabled: false }, unexpectedRequests)
  await fulfillJson(page, '/api/version', { version: 'fixture' }, unexpectedRequests)
  await fulfillJson(page, '/api/settings', settings, unexpectedRequests, ['GET', 'HEAD', 'PUT'])
  await fulfillJson(page, '/api/settings/observability', observability, unexpectedRequests)
  await fulfillJson(page, '/api/credentials/status', {
    configured: {}, source: {}, encryption_configured: true,
  }, unexpectedRequests)
  await fulfillJson(page, '/api/credentials/env-status', {}, unexpectedRequests)
  await fulfillJson(page, '/api/deeper-notebook/gmail/status', {
    connected: false, email_address: null, has_client_credentials: false,
  }, unexpectedRequests)
  await fulfillJson(page, '/api/deeper-notebook/vaults', [], unexpectedRequests)
  await fulfillJson(page, '/api/deeper-notebook/overlay/notes', [], unexpectedRequests)
  await fulfillJson(page, '/api/notebooks', [], unexpectedRequests)
  await fulfillJson(page, '/api/transformations', [], unexpectedRequests)
  await fulfillJson(page, '/api/episode-profiles', [], unexpectedRequests)
  await fulfillJson(page, '/api/local-models/health', {
    overall: 'healthy', models: [],
  }, unexpectedRequests)
  await fulfillJson(page, '/api/system/db-repair-needed', { needs_repair: false }, unexpectedRequests)
  await fulfillJson(page, '/api/system/network-status', {
    status: 'online', forced_offline: false, local_fallback_model: null, checked_epoch_ms: 0,
  }, unexpectedRequests)
  await fulfillJson(page, '/api/updates/check', updateStatus, unexpectedRequests)
  await fulfillJson(page, '/api/runtime/snapshot', runtimeSnapshot, unexpectedRequests)
  await fulfillJson(page, '/healthz/deep', {
    status: 'healthy',
    checks: {
      database: { status: 'ready', ok: true, error: null },
      migrations: { status: 'ready', ok: true, error: null },
      embedding_model: { status: 'ready', ok: true, error: null },
      chat_model: { status: 'ready', ok: true, error: null },
      command_registry: { status: 'ready', ok: true, error: null },
    },
  }, unexpectedRequests)
  await fulfillJson(page, '/api/healthz/deep', {
    status: 'healthy',
    checks: {
      database: { status: 'ready', ok: true, error: null },
      migrations: { status: 'ready', ok: true, error: null },
      embedding_model: { status: 'ready', ok: true, error: null },
      chat_model: { status: 'ready', ok: true, error: null },
      command_registry: { status: 'ready', ok: true, error: null },
    },
  }, unexpectedRequests)
  await page.route((url) => url.pathname === '/api/deeper-notebook/theme', async (route) => {
    const method = route.request().method()
    if (method === 'GET' || method === 'HEAD') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ theme, available: THEME_CATALOG.map(entry => entry.id) }),
      })
      return
    }

    if (method === 'POST') {
      const requestTheme = route.request().postDataJSON()?.theme
      if (!isThemeId(requestTheme)) {
        unexpectedRequests.push(requestLabel(route))
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Unknown fixture theme' }),
        })
        return
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ theme: requestTheme, available: THEME_CATALOG.map(entry => entry.id) }),
      })
      return
    }

    unexpectedRequests.push(requestLabel(route))
    await route.fulfill({
      status: 405,
      contentType: 'application/json',
      headers: { Allow: 'GET, HEAD, POST' },
      body: JSON.stringify({ detail: 'Method not allowed by theme visual fixture' }),
    })
  })

  return { unexpectedRequests }
}
