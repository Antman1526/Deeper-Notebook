import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LuminousAppShell } from './LuminousAppShell'
import { useAuth } from '@/lib/hooks/use-auth'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'

const push = vi.fn()
const openSourceDialog = vi.fn()
const openNotebookDialog = vi.fn()
const openPodcastDialog = vi.fn()
const logout = vi.fn()

vi.mock('next/navigation', () => ({
  usePathname: () => '/knowledge/workspace',
  useRouter: () => ({ push }),
}))

vi.mock('@/lib/hooks/use-auth', () => ({
  useAuth: vi.fn(),
}))

vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: vi.fn(),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'common.create': 'Create',
      'common.source': 'Source',
      'common.notebook': 'Notebook',
      'common.podcast': 'Podcast',
      'common.signOut': 'Sign out',
      'common.quickActions': 'Quick actions',
    }[key] ?? key),
    language: 'en-US',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('@/lib/hooks/use-media-query', () => ({
  useIsDesktop: () => true,
}))

vi.mock('@/components/deeper-notebook/ThemeSwitcher', () => ({
  ThemeSwitcher: ({ iconOnly }: { iconOnly?: boolean }) => (
    <button type="button">{iconOnly ? 'Theme icon' : 'Theme'}</button>
  ),
}))

vi.mock('@/components/common/LanguageToggle', () => ({
  LanguageToggle: ({ iconOnly }: { iconOnly?: boolean }) => (
    <button type="button">{iconOnly ? 'Language icon' : 'Language'}</button>
  ),
}))

vi.mock('@/components/deeper-notebook/GmailSidebarButton', () => ({
  GmailSidebarButton: ({ iconOnly }: { iconOnly?: boolean }) => (
    <button type="button">{iconOnly ? 'Gmail icon' : 'Gmail'}</button>
  ),
}))

vi.mock('@/components/chat/LocalModelHealthBadges', () => ({
  LocalModelHealthBadges: () => <div data-testid="local-model-health">Local model health</div>,
}))

vi.mock('@/components/layout/SetupBanner', () => ({
  SetupBanner: () => <div data-testid="setup-banner">Setup banner</div>,
}))

vi.mock('@/components/layout/DbRepairBanner', () => ({
  DbRepairBanner: () => <div data-testid="db-repair-banner">DB repair banner</div>,
}))

vi.mock('@/components/layout/UpdateBanner', () => ({
  UpdateBanner: () => <div data-testid="update-banner">Update banner</div>,
}))

vi.mock('@/components/layout/NetworkStatusBadge', () => ({
  NetworkStatusBadge: () => <div data-testid="network-banner">Network banner</div>,
}))

vi.mock('@/components/guided-tips', () => ({
  GuidedTipsProvider: () => <div data-testid="guided-tips">Guided tips</div>,
}))

vi.mock('@/components/podcasts/GlobalAudioPlayer', () => ({
  GlobalAudioPlayer: () => <div data-testid="audio-player">Audio player</div>,
}))

vi.mock('./shell.css', () => ({}))

describe('LuminousAppShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ logout } as never)
    vi.mocked(useCreateDialogs).mockReturnValue({
      openSourceDialog,
      openNotebookDialog,
      openPodcastDialog,
    })
  })

  it('preserves the navigation, utilities, and one editorial page slot', () => {
    render(
      <LuminousAppShell>
        <div data-testid="page-content">Page content</div>
      </LuminousAppShell>,
    )

    expect(screen.getByRole('navigation', { name: 'Primary tools' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: 'Notebook index' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled()
    expect(screen.getByRole('heading', { name: 'Deeper Notebook' })).toBeVisible()
    expect(screen.getByTestId('global-audio-player')).toBeInTheDocument()

    const expectedRoutes = [
      '/sources', '/capture', '/notebooks', '/knowledge', '/search',
      '/studio', '/podcasts', '/study', '/settings/api-keys',
      '/transformations', '/settings', '/settings/mcp',
      '/settings/launcher-prefs', '/advanced',
    ]
    expect(screen.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(expectedRoutes)

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Source' }))
    expect(openSourceDialog).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Notebook' }))
    expect(openNotebookDialog).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Podcast' }))
    expect(openPodcastDialog).toHaveBeenCalledTimes(1)

    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(logout).toHaveBeenCalledTimes(1)

    expect(screen.getByRole('button', { name: 'Theme' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Language' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gmail' })).toBeInTheDocument()
    expect(screen.getByTestId('local-model-health')).toBeInTheDocument()
    expect(screen.getByText('v—')).toBeInTheDocument()
    expect(screen.getByTestId('command-shortcut')).toHaveTextContent(/Ctrl\+K|⌘K/)

    expect(screen.getByTestId('setup-banner')).toBeInTheDocument()
    expect(screen.getByTestId('db-repair-banner')).toBeInTheDocument()
    expect(screen.getByTestId('update-banner')).toBeInTheDocument()
    expect(screen.getByTestId('network-banner')).toBeInTheDocument()
    expect(screen.getByTestId('guided-tips')).toBeInTheDocument()
    expect(screen.getByTestId('audio-player')).toBeInTheDocument()
    expect(screen.getAllByTestId('page-content')).toHaveLength(1)
    expect(document.querySelectorAll('.dn-editorial-canvas')).toHaveLength(1)
  })
})
