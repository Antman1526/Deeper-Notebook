import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceHome } from './WorkspaceHome'

// v0.8.130 — strings with inline markup (the shortcut chip, the data path) render
// through RichText, which needs the real en-US sentence with its tags. Every other
// key is echoed, as in the global mock.
vi.mock('@/lib/hooks/use-translation', async () => {
  const { enUS } = await import('@/lib/locales/en-US')
  const t = (key: string): string => {
    let node: unknown = enUS
    for (const part of key.split('.')) node = (node as Record<string, unknown> | undefined)?.[part]
    return typeof node === 'string' && /<[a-zA-Z][\w-]*\s*\/?>/.test(node) ? node : key
  }
  return { useTranslation: () => ({ t, i18n: { language: 'en-US' }, language: 'en-US', setLanguage: async () => 'en-US' }) }
})

// v0.8.130 — the home tip printed both platforms' shortcuts ("⌘K / Ctrl+K") in
// unstyled <kbd> tags; it now shows the current platform's key in the shared chip.
const runtimeSnapshot = {
  schema_version: 'runtime-snapshot-v1' as const,
  status: 'ready' as const,
  reasons: [] as const,
  readiness: { state: 'ready' as const, database: 'online' as const, migrations: 'applied' as const },
  startup: { state: 'ready' as const, stages: [] },
  updates: { state: 'ready' as const, enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready' as const, ready: 1, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready' as const, projected: 1, unchanged: 0, failed: 0 },
  backup: { state: 'ready' as const, file_count: 1, newest_age_seconds: 5 },
}

function renderHome() {
  render(
    <WorkspaceHome
      status="ready"
      recentNotebooks={[]}
      onOpenStudio={vi.fn()}
      onCreateNotebook={vi.fn()}
      onCreatePodcast={vi.fn()}
      onAsk={vi.fn()}
      notebooksLoading={false}
      runtimeSnapshot={runtimeSnapshot}
      runtimeSnapshotLoading={false}
      dataPath="~/.deeper-notebook/"
    />,
  )
}

describe('WorkspaceHome command hint', () => {
  const originalPlatform = window.navigator.platform
  const setPlatform = (platform: string) =>
    Object.defineProperty(window.navigator, 'platform', { value: platform, configurable: true })
  afterEach(() => setPlatform(originalPlatform))

  it('shows only ⌘K on macOS, in the shared key chip', () => {
    setPlatform('MacIntel')
    renderHome()
    expect(screen.getByText('⌘K')).toHaveAttribute('data-slot', 'kbd')
    expect(screen.queryByText(/Ctrl\+K/)).toBeNull()
  })

  it('shows only Ctrl+K elsewhere', () => {
    setPlatform('Win32')
    renderHome()
    expect(screen.getByText('Ctrl+K')).toHaveAttribute('data-slot', 'kbd')
    expect(screen.queryByText(/⌘K/)).toBeNull()
  })
})
