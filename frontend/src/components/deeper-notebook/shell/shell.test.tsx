import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LuminousAppShell } from './LuminousAppShell'
import { FolioPage } from '../folio/FolioPage'
import { useAuth } from '@/lib/hooks/use-auth'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'

const push = vi.fn()
const openSourceDialog = vi.fn()
const openNotebookDialog = vi.fn()
const openPodcastDialog = vi.fn()
const logout = vi.fn()
let currentPathname = '/knowledge/workspace'

vi.mock('next/navigation', () => ({
  usePathname: () => currentPathname,
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
  const openCreateMenu = () => {
    fireEvent.keyDown(screen.getByRole('button', { name: 'Create' }), { key: 'ArrowDown' })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    currentPathname = '/knowledge/workspace'
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
    expect(screen.getByText('Deeper Notebook', { selector: '.dn-command-title' })).toBeVisible()
    expect(screen.getByTestId('global-audio-player')).toBeInTheDocument()

    const expectedRoutes = [
      '/sources', '/capture', '/notebooks', '/knowledge', '/search',
      '/studio', '/podcasts', '/study', '/settings/api-keys',
      '/transformations', '/settings', '/settings/mcp',
      '/settings/launcher-prefs', '/advanced',
    ]
    expect(screen.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(expectedRoutes)

    openCreateMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Source' }))
    expect(openSourceDialog).toHaveBeenCalledTimes(1)

    openCreateMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Notebook' }))
    expect(openNotebookDialog).toHaveBeenCalledTimes(1)

    openCreateMenu()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Podcast' }))
    expect(openPodcastDialog).toHaveBeenCalledTimes(1)

    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(logout).toHaveBeenCalledTimes(1)

    expect(screen.getByRole('button', { name: 'Theme icon' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Language icon' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Gmail icon' })).toBeInTheDocument()
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

  it('leaves the page heading to the folio route', () => {
    render(
      <LuminousAppShell>
        <FolioPage title="Research workspace">
          <p>Local research.</p>
        </FolioPage>
      </LuminousAppShell>,
    )

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1, name: 'Research workspace' })).toBeInTheDocument()
  })

  it('keeps theme, language, Gmail, auth, health, and version controls in the mobile dock alternative', () => {
    render(<LuminousAppShell><div data-testid="page-content">Page content</div></LuminousAppShell>)

    const utilities = document.querySelector('[data-mobile-mode="utility-row"]')
    expect(utilities).toBeInTheDocument()
    const mobileUtilities = within(utilities as HTMLElement)
    expect(mobileUtilities.getByRole('button', { name: 'Theme icon' })).toBeInTheDocument()
    expect(mobileUtilities.getByRole('button', { name: 'Language icon' })).toBeInTheDocument()
    expect(mobileUtilities.getByRole('button', { name: 'Gmail icon' })).toBeInTheDocument()
    expect(mobileUtilities.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    expect(mobileUtilities.getByTestId('local-model-health')).toBeInTheDocument()
    expect(mobileUtilities.getByText('v—')).toBeInTheDocument()
  })

  it('keeps exactly one canonical guided-tip anchor for search', () => {
    render(<LuminousAppShell><div data-testid="page-content">Page content</div></LuminousAppShell>)

    const searchAnchors = document.querySelectorAll('[data-guided-tip-anchor="/search"]')
    expect(searchAnchors).toHaveLength(1)
    expect(searchAnchors[0]).toBe(screen.getByRole('link', { name: 'navigation.askAndSearch' }))
  })

  it('marks only the most specific nested navigation route as current', () => {
    currentPathname = '/settings/api-keys'
    render(<LuminousAppShell><div data-testid="page-content">Page content</div></LuminousAppShell>)

    const currentLinks = screen.getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page')
    expect(currentLinks).toHaveLength(1)
    expect(currentLinks[0]).toHaveAttribute('href', '/settings/api-keys')
    expect(document.querySelectorAll('#onp-sidebar-active')).toHaveLength(1)
  })

  it('uses Radix menu keyboard focus, escape, outside dismissal, and callbacks', async () => {
    render(<LuminousAppShell><div data-testid="page-content">Page content</div></LuminousAppShell>)

    const trigger = screen.getByRole('button', { name: 'Create' })
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })

    const source = screen.getByRole('menuitem', { name: 'Source' })
    const notebook = screen.getByRole('menuitem', { name: 'Notebook' })
    expect(source).toHaveFocus()
    fireEvent.keyDown(source, { key: 'ArrowDown' })
    await waitFor(() => expect(notebook).toHaveFocus())

    fireEvent.keyDown(notebook, { key: 'Escape' })
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(screen.queryByRole('menuitem', { name: 'Source' })).not.toBeInTheDocument()

    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    expect(screen.getByRole('menuitem', { name: 'Source' })).toHaveFocus()
    const outside = document.createElement('div')
    document.body.appendChild(outside)
    await new Promise((resolve) => setTimeout(resolve, 0))
    fireEvent.pointerDown(outside, { button: 0 })
    await waitFor(() => expect(screen.queryByRole('menuitem', { name: 'Source' })).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
    outside.remove()
  })

  it('keeps editorial route content mounted while Focus mode exposes a keyboard-reachable exit', () => {
    render(<LuminousAppShell><div data-testid="page-content">Page content</div></LuminousAppShell>)

    fireEvent.keyDown(document, { key: 'f', ctrlKey: true, shiftKey: true })

    expect(screen.getByTestId('page-content')).toBeInTheDocument()
    expect(document.documentElement.dataset.dnFocusMode).toBe('true')
    const exit = screen.getByRole('button', { name: 'Exit Focus mode' })
    expect(exit).toBeVisible()
    exit.focus()
    expect(exit).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByRole('button', { name: 'Enter Focus mode' })).toBeInTheDocument()
  })

  it('keeps navigation and utility paths keyboard reachable while Focus mode is active', () => {
    render(<LuminousAppShell><div data-testid="page-content">Page content</div></LuminousAppShell>)

    fireEvent.click(screen.getByRole('button', { name: 'Enter Focus mode' }))

    const navigationLink = screen.getByRole('link', { name: 'navigation.sources' })
    const utility = screen.getAllByRole('button', { name: 'Sign out' })[0]
    expect(navigationLink).toBeInTheDocument()
    expect(utility).toBeInTheDocument()

    navigationLink.focus()
    expect(navigationLink).toHaveFocus()
    utility.focus()
    expect(utility).toHaveFocus()
  })
})
