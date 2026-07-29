import type { Page, Route } from '@playwright/test'

export interface KnowledgeFixtureState {
  workspace: Record<string, unknown>
}

const file = {
  id: 'vault_file:plan',
  note_id: 'note:plan',
  vault_id: 'vault:fixture',
  relative_path: 'pages/plan.md',
  file_kind: 'markdown',
  format: 'obsidian',
  content_hash: 'a'.repeat(64),
  size_bytes: 34,
  modified_ns: 1,
  encoding: 'utf-8',
  newline: 'lf',
  parse_status: 'parsed',
  deleted_state: 'present',
}

const page = {
  file,
  note: {
    id: 'note:plan',
    title: 'Plan',
    content: '# Plan\n\n[[Evidence]]',
    source_format: 'obsidian',
    properties: { status: 'active' },
    tags: ['research'],
  },
  blocks: [
    {
      markdown: '# Plan',
      plain_text: 'Plan',
      heading_path: ['Plan'],
      block_kind: 'heading',
    },
  ],
  tasks: [],
  outgoing_links: [
    {
      id: 'note_link:plan-evidence',
      source_note_id: 'note:plan',
      target_note_id: 'note:evidence',
      target_note_title: 'Evidence',
      target_relative_path: 'pages/evidence.md',
      target_text: 'Evidence',
      link_kind: 'wikilink',
      resolved: true,
      source_start: 8,
      source_end: 20,
    },
  ],
  backlinks: [],
}

const fixturePagePaths = [
  '/api/deeper-notebook/vaults/vault%3Afixture/pages/note%3Aplan',
  '/api/deeper-notebook/vaults/vault:fixture/pages/note:plan',
] as const

type FixturePageRoute = 'page' | 'outgoing' | 'backlinks'

function matchFixturePageRoute(pathname: string): FixturePageRoute | null {
  for (const pagePath of fixturePagePaths) {
    if (pathname === pagePath) return 'page'
    if (pathname === `${pagePath}/outgoing`) return 'outgoing'
    if (pathname === `${pagePath}/backlinks`) return 'backlinks'
  }
  return null
}

export function initialKnowledgeFixtureState(): KnowledgeFixtureState {
  return {
    workspace: {
      version: 1,
      active_pane_id: 'pane-1',
      next_id: 2,
      panes: {
        'pane-1': {
          id: 'pane-1',
          active_tab_id: null,
          tabs: [],
        },
      },
      layout: { type: 'pane', pane_id: 'pane-1' },
    },
  }
}

async function fulfillJson(
  page: Page,
  pathname: string,
  body: unknown,
  unexpectedApiTraffic: string[],
  allowedMethods: readonly string[] = ['GET', 'HEAD'],
): Promise<void> {
  await page.route((url) => url.pathname === pathname, async (route) => {
    if (
      !(await allowRequestMethod(route, allowedMethods, unexpectedApiTraffic))
    ) {
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

function requestLabel(route: Route): string {
  const request = route.request()
  return `${request.method()} ${new URL(request.url()).pathname}`
}

async function allowRequestMethod(
  route: Route,
  allowedMethods: readonly string[],
  unexpectedApiTraffic: string[],
): Promise<boolean> {
  if (allowedMethods.includes(route.request().method())) {
    return true
  }

  unexpectedApiTraffic.push(requestLabel(route))
  await route.fulfill({
    status: 405,
    contentType: 'application/json',
    headers: { Allow: allowedMethods.join(', ') },
    body: JSON.stringify({ detail: 'Method not allowed by E2E fixture' }),
  })
  return false
}

export async function installKnowledgeShellMocks(
  page: Page,
  unexpectedApiTraffic: string[] = [],
): Promise<void> {
  await page.context().addCookies([
    {
      name: 'wizard_completed',
      value: 'true',
      domain: '127.0.0.1',
      path: '/',
    },
  ])

  await page.route('**/api/**', async (route) => {
    unexpectedApiTraffic.push(requestLabel(route))
    await route.fulfill({
      status: 501,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unhandled API request in E2E fixture' }),
    })
  })

  await fulfillJson(page, '/config', { apiUrl: '' }, unexpectedApiTraffic)
  await fulfillJson(
    page,
    '/api/config',
    {
      version: 'fixture',
      latestVersion: null,
      hasUpdate: false,
      dbStatus: 'healthy',
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/auth/status',
    { auth_required: false },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/version',
    { version: 'fixture' },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/local-models/health',
    {
      overall: 'healthy',
      models: [],
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(page, '/api/notebooks', [], unexpectedApiTraffic)
  await fulfillJson(page, '/api/sources', [], unexpectedApiTraffic)
  await fulfillJson(page, '/api/episode-profiles', [], unexpectedApiTraffic)
  await fulfillJson(page, '/api/speaker-profiles', [], unexpectedApiTraffic)
  await fulfillJson(
    page,
    '/api/deeper-notebook/gmail/status',
    {
      connected: false,
      email_address: null,
      has_client_credentials: false,
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/credentials/status',
    {
      configured: {},
      source: {},
      encryption_configured: false,
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/credentials/env-status',
    {},
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/system/db-repair-needed',
    { needs_repair: false },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/updates/check',
    {
      current: 'fixture',
      latest: null,
      update_available: false,
      skipped: false,
      skipped_version: null,
      html_url: null,
      published_at: null,
      enabled: false,
      last_check: null,
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/system/network-status',
    {
      status: 'online',
      forced_offline: false,
      local_fallback_model: null,
      checked_epoch_ms: 0,
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(page, '/api/transformations', [], unexpectedApiTraffic)
  await fulfillJson(page, '/api/settings', {}, unexpectedApiTraffic)
  await fulfillJson(
    page,
    '/healthz/deep',
    {
      status: 'healthy',
      checks: {
        database: { status: 'ready', ok: true, error: null },
        migrations: { status: 'ready', ok: true, error: null },
        embedding_model: { status: 'ready', ok: true, error: null },
        chat_model: { status: 'ready', ok: true, error: null },
        command_registry: { status: 'ready', ok: true, error: null },
      },
    },
    unexpectedApiTraffic,
  )
  await fulfillJson(
    page,
    '/api/healthz/deep',
    {
      status: 'healthy',
      checks: {
        database: { status: 'ready', ok: true, error: null },
        migrations: { status: 'ready', ok: true, error: null },
        embedding_model: { status: 'ready', ok: true, error: null },
        chat_model: { status: 'ready', ok: true, error: null },
        command_registry: { status: 'ready', ok: true, error: null },
      },
    },
    unexpectedApiTraffic,
  )
}

export async function fulfillKnowledgeRequest(
  route: Route,
  state: KnowledgeFixtureState,
  unexpectedApiTraffic: string[] = [],
): Promise<void> {
  const request = route.request()
  const path = new URL(request.url()).pathname
  const method = request.method()
  const pageRoute = matchFixturePageRoute(path)
  let payload: unknown

  if (path.endsWith('/deeper-notebook/workspace/knowledge')) {
    if (
      !(await allowRequestMethod(
        route,
        ['GET', 'HEAD', 'PUT'],
        unexpectedApiTraffic,
      ))
    ) {
      return
    }
    if (method === 'PUT') {
      state.workspace = request.postDataJSON() as Record<string, unknown>
    }
    payload = state.workspace
  } else if (path.endsWith('/deeper-notebook/vaults')) {
    if (
      !(await allowRequestMethod(route, ['GET', 'HEAD'], unexpectedApiTraffic))
    ) {
      return
    }
    payload = [
      {
        id: 'vault:fixture',
        name: 'Fixture vault',
        format_mode: 'obsidian',
        state: 'ready-read-only',
        parent_vault_id: null,
        watch_enabled: false,
      },
    ]
  } else if (
    path.endsWith('/vaults/vault%3Afixture/files') ||
    path.endsWith('/vaults/vault:fixture/files')
  ) {
    if (
      !(await allowRequestMethod(route, ['GET', 'HEAD'], unexpectedApiTraffic))
    ) {
      return
    }
    payload = [file]
  } else if (pageRoute !== null) {
    if (
      !(await allowRequestMethod(route, ['GET', 'HEAD'], unexpectedApiTraffic))
    ) {
      return
    }
    payload = pageRoute === 'outgoing'
      ? page.outgoing_links
      : pageRoute === 'backlinks'
        ? page.backlinks
        : page
  } else if (
    path.endsWith('/vaults/vault%3Afixture/graph') ||
    path.endsWith('/vaults/vault:fixture/graph')
  ) {
    if (
      !(await allowRequestMethod(route, ['GET', 'HEAD'], unexpectedApiTraffic))
    ) {
      return
    }
    payload = {
      nodes: [
        {
          id: 'note:plan',
          title: 'Plan',
          source_format: 'obsidian',
          external_state: 'current',
        },
      ],
      edges: [],
    }
  } else {
    await route.fallback()
    return
  }

  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}
