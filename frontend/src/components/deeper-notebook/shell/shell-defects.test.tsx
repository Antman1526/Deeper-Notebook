import { act, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuth } from '@/lib/hooks/use-auth'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { DEFAULT_DISPLAY_PREFERENCES, useDisplayPreferencesStore } from '@/lib/stores/display-preferences-store'

import { CommandBar } from './CommandBar'
import { FocusModeControl } from './FocusModeControl'
import { InstrumentDock } from './InstrumentDock'

// Phase 0 shell defects (UI audit 2026-09-30, T0-3 / T0-7):
//  - the dock CSS hides the LABEL of the Create and Sign-out buttons, so the
//    label must be addressable on its own or the icon disappears with it;
//  - the `v—` placeholder must not render when there is no desktop version;
//  - keyboard hints show ONE platform-correct shortcut, without a duplicate icon.

vi.mock('next/navigation', () => ({
  usePathname: () => '/notebooks',
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/lib/hooks/use-auth', () => ({ useAuth: vi.fn() }))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({ useCreateDialogs: vi.fn() }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'common.create': 'Create',
      'common.signOut': 'Sign out',
      'common.quickActions': 'Quick actions',
    }[key] ?? key),
  }),
}))
vi.mock('@/components/deeper-notebook/ThemeSwitcher', () => ({
  ThemeSwitcher: () => <button type="button">Theme icon</button>,
}))
vi.mock('@/components/common/LanguageToggle', () => ({
  LanguageToggle: () => <button type="button">Language icon</button>,
}))
vi.mock('@/components/deeper-notebook/GmailSidebarButton', () => ({
  GmailSidebarButton: () => <button type="button">Gmail icon</button>,
}))
vi.mock('@/components/chat/LocalModelHealthBadges', () => ({
  LocalModelHealthBadges: () => <div data-testid="local-model-health" />,
}))

function setPlatform(platform: string) {
  Object.defineProperty(window.navigator, 'platform', { value: platform, configurable: true })
}

declare global {
  interface Window {
    DEEPER_NOTEBOOK_VERSION?: string
  }
}

describe('InstrumentDock', () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({ logout: vi.fn() } as never)
    vi.mocked(useCreateDialogs).mockReturnValue({
      openSourceDialog: vi.fn(),
      openNotebookDialog: vi.fn(),
      openPodcastDialog: vi.fn(),
    })
  })

  afterEach(() => {
    delete window.DEEPER_NOTEBOOK_VERSION
  })

  it('keeps the Create icon outside the label element the dock CSS hides', () => {
    render(<InstrumentDock />)
    const create = screen.getByRole('button', { name: 'Create' })

    const icon = create.querySelector('svg')
    expect(icon).not.toBeNull()
    expect(icon?.closest('.dn-dock-label')).toBeNull()
    expect(create.querySelector('.dn-dock-label')).toHaveTextContent('Create')
  })

  it('marks the Sign out text as the label so only the text is hidden in the narrow dock', () => {
    render(<InstrumentDock />)
    const signOut = screen.getByRole('button', { name: 'Sign out' })

    expect(signOut.querySelector('svg')?.closest('.dn-dock-label')).toBeNull()
    expect(signOut.querySelector('.dn-dock-label')).toHaveTextContent('Sign out')
  })

  it('renders no version placeholder when the desktop bridge provides no version', () => {
    render(<InstrumentDock />)
    expect(document.querySelector('.dn-dock-version')).toBeNull()
    expect(screen.queryByText('v—')).not.toBeInTheDocument()
  })

  it('picks up a version the desktop app injects after the page has loaded', () => {
    // pywebview injects window.DEEPER_NOTEBOOK_VERSION from its `loaded` handler,
    // which fires AFTER React has hydrated and run its mount effects.
    vi.useFakeTimers()
    try {
      render(<InstrumentDock />)
      expect(document.querySelector('.dn-dock-version')).toBeNull()

      window.DEEPER_NOTEBOOK_VERSION = '2.0.0'
      act(() => {
        vi.advanceTimersByTime(600)
      })

      expect(screen.getByText('v2.0.0')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows the desktop version in the dock and in the mobile utility row', () => {
    window.DEEPER_NOTEBOOK_VERSION = '1.2.3'
    render(<InstrumentDock />)

    expect(screen.getByText('v1.2.3')).toBeInTheDocument()
    const utilities = document.querySelector('[data-mobile-mode="utility-row"]')?.closest('.dn-dock-utilities')
    expect(utilities).not.toBeNull()
    expect(within(utilities as HTMLElement).getByText('v1.2.3')).toBeInTheDocument()
  })
})

describe('shell keyboard hints', () => {
  const originalPlatform = window.navigator.platform

  beforeEach(() => {
    useDisplayPreferencesStore.setState(DEFAULT_DISPLAY_PREFERENCES)
  })

  afterEach(() => {
    setPlatform(originalPlatform)
  })

  it('shows a single ⌘K hint on macOS, with no duplicate icon', () => {
    setPlatform('MacIntel')
    render(<CommandBar />)
    const chip = screen.getByTestId('command-shortcut')

    expect(chip).toHaveTextContent(/^⌘K$/)
    expect(chip.querySelector('svg')).toBeNull()
  })

  it('shows Ctrl+K on other platforms', () => {
    setPlatform('Win32')
    render(<CommandBar />)
    expect(screen.getByTestId('command-shortcut')).toHaveTextContent(/^Ctrl\+K$/)
  })

  it('shows only the macOS Focus shortcut on macOS', () => {
    setPlatform('MacIntel')
    render(<FocusModeControl />)
    const control = screen.getByTestId('focus-mode-control')

    expect(control.querySelector('kbd')).toHaveTextContent(/^⌘⇧F$/)
    expect(control.getAttribute('title')).toContain('⌘⇧F')
    expect(control.getAttribute('title')).not.toContain('Ctrl')
  })

  // v0.8.130 — both chips use the shared Kbd primitive (they were hand-rolled, one at 10px).
  it('renders both shortcut chips with the shared key chip', () => {
    setPlatform('MacIntel')
    render(<CommandBar />) // it renders FocusModeControl itself
    expect(screen.getByTestId('command-shortcut')).toHaveAttribute('data-slot', 'kbd')
    expect(screen.getByTestId('focus-mode-control').querySelector('kbd')).toHaveAttribute('data-slot', 'kbd')
  })

  it('shows only the Ctrl Focus shortcut elsewhere', () => {
    setPlatform('Win32')
    render(<FocusModeControl />)
    const control = screen.getByTestId('focus-mode-control')

    expect(control.querySelector('kbd')).toHaveTextContent(/^Ctrl\+Shift\+F$/)
    expect(control.getAttribute('title')).not.toContain('⌘')
  })
})
