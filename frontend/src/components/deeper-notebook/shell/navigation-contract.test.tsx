import type { TFunction } from 'i18next'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CREATE_TARGETS, getNavigation } from '@/components/layout/AppSidebar'
import { WorkspaceAppShell } from '@/components/deeper-notebook/workspace/WorkspaceAppShell'

const dialogSpies = vi.hoisted(() => ({
  openSourceDialog: vi.fn(),
  openNotebookDialog: vi.fn(),
  openPodcastDialog: vi.fn(),
}))

vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => dialogSpies,
}))
vi.mock('@/components/chat/LocalModelHealthBadges', () => ({
  LocalModelHealthBadges: () => <div data-testid="local-model-health" />,
}))
vi.mock('@/components/deeper-notebook/ThemeSwitcher', () => ({
  ThemeSwitcher: () => <button type="button">Theme</button>,
}))
vi.mock('@/components/deeper-notebook/GmailSidebarButton', () => ({
  GmailSidebarButton: () => <button type="button">Gmail</button>,
}))
vi.mock('@/components/common/LanguageToggle', () => ({
  LanguageToggle: () => <button type="button">Language</button>,
}))
vi.mock('@/components/layout/SetupBanner', () => ({ SetupBanner: () => null }))
vi.mock('@/components/layout/DbRepairBanner', () => ({ DbRepairBanner: () => null }))
vi.mock('@/components/layout/UpdateBanner', () => ({ UpdateBanner: () => null }))
vi.mock('@/components/layout/NetworkStatusBadge', () => ({ NetworkStatusBadge: () => null }))
vi.mock('@/components/guided-tips', () => ({ GuidedTipsProvider: () => null }))
vi.mock('@/components/podcasts/GlobalAudioPlayer', () => ({ GlobalAudioPlayer: () => null }))

describe('Luminous Folio navigation parity contract', () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH
  })

  it('preserves the existing navigation href order and create targets', () => {
    const previousFlag = process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '1'
    const t = ((key: string) => key) as TFunction
    try {
      const sections = getNavigation(t)

      expect(sections.flatMap(section => section.items.map(item => item.href))).toEqual([
        '/sources', '/capture', '/notebooks', '/knowledge', '/search',
        '/studio', '/podcasts', '/study', '/settings/api-keys',
        '/transformations', '/settings', '/settings/mcp',
        '/settings/launcher-prefs', '/advanced',
      ])
      expect(CREATE_TARGETS).toEqual(['source', 'notebook', 'podcast'])
    } finally {
      if (previousFlag === undefined) delete process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH
      else process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = previousFlag
    }
  })

  it('keeps V2 href order and one guided-tip anchor per destination', () => {
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '1'
    render(<WorkspaceAppShell><div data-testid="page-slot" /></WorkspaceAppShell>)

    const expectedRoutes = [
      '/', '/sources', '/capture', '/notebooks', '/knowledge', '/search',
      '/studio', '/podcasts', '/study', '/settings/api-keys',
      '/transformations', '/settings', '/settings/mcp',
      '/settings/launcher-prefs', '/advanced',
    ]
    expect(screen.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(
      expectedRoutes.slice(1),
    )
    const guidedDestinations = [...expectedRoutes, '/settings/local-models']
    expect(guidedDestinations.map((href) => document.querySelectorAll(`[data-guided-tip-anchor="${href}"]`).length))
      .toEqual(guidedDestinations.map(() => 1))
    expect(screen.getAllByTestId('focus-mode-control')).toHaveLength(1)
  })

  it('dispatches each V2 create target exactly once', () => {
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '1'
    dialogSpies.openSourceDialog.mockClear()
    dialogSpies.openNotebookDialog.mockClear()
    dialogSpies.openPodcastDialog.mockClear()
    render(<WorkspaceAppShell><div data-testid="page-slot" /></WorkspaceAppShell>)

    const create = screen.getByRole('button', { name: 'common.create' })
    for (const target of ['common.source', 'common.notebook', 'common.podcast']) {
      fireEvent.keyDown(create, { key: 'ArrowDown' })
      fireEvent.click(screen.getByRole('menuitem', { name: target }))
    }

    expect(dialogSpies.openSourceDialog).toHaveBeenCalledTimes(1)
    expect(dialogSpies.openNotebookDialog).toHaveBeenCalledTimes(1)
    expect(dialogSpies.openPodcastDialog).toHaveBeenCalledTimes(1)
  })
})
