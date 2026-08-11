import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AppShell } from './AppShell'
import { DEFAULT_DISPLAY_PREFERENCES, useDisplayPreferencesStore } from '@/lib/stores/display-preferences-store'

vi.mock('./AppSidebar', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./AppSidebar')>()
  return {
    ...actual,
    AppSidebar: () => <aside data-testid="legacy-sidebar">Legacy sidebar</aside>,
  }
})

vi.mock('./SetupBanner', () => ({ SetupBanner: () => <div data-testid="legacy-setup" /> }))
vi.mock('./DbRepairBanner', () => ({ DbRepairBanner: () => <div data-testid="legacy-db-repair" /> }))
vi.mock('./UpdateBanner', () => ({ UpdateBanner: () => <div data-testid="legacy-update" /> }))
vi.mock('./NetworkStatusBadge', () => ({ NetworkStatusBadge: () => <div data-testid="legacy-network" /> }))
vi.mock('@/components/guided-tips', () => ({ GuidedTipsProvider: () => <div data-testid="legacy-guided" /> }))
vi.mock('@/components/podcasts/GlobalAudioPlayer', () => ({ GlobalAudioPlayer: () => <div data-testid="legacy-audio" /> }))
vi.mock('@/components/deeper-notebook/shell/shell.css', () => ({}))
vi.mock('@/components/chat/LocalModelHealthBadges', () => ({ LocalModelHealthBadges: () => null }))
vi.mock('@/components/deeper-notebook/ThemeSwitcher', () => ({ ThemeSwitcher: () => <button type="button">Theme</button> }))
vi.mock('@/components/deeper-notebook/GmailSidebarButton', () => ({ GmailSidebarButton: () => <button type="button">Gmail</button> }))
vi.mock('@/components/common/LanguageToggle', () => ({ LanguageToggle: () => <button type="button">Language</button> }))

describe('AppShell feature switch', () => {
  beforeEach(() => {
    useDisplayPreferencesStore.setState(DEFAULT_DISPLAY_PREFERENCES)
  })

  afterEach(() => {
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO
  })

  it('retains the private legacy shell when the flag is off', () => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '0'
    render(<AppShell><div data-testid="legacy-page">Legacy page</div></AppShell>)

    expect(screen.getByTestId('legacy-sidebar')).toBeInTheDocument()
    expect(screen.getByTestId('legacy-page')).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary tools' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Enter Focus mode' })).toBeInTheDocument()
  })

  it('keeps the legacy utility route mounted when Focus mode is active', () => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '0'
    render(<AppShell><div data-testid="legacy-page">Legacy page</div></AppShell>)

    fireEvent.click(screen.getByRole('button', { name: 'Enter Focus mode' }))

    expect(screen.getByTestId('legacy-sidebar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exit Focus mode' })).toBeInTheDocument()
  })

  it('renders only the Luminous shell when the flag is on', () => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '1'
    render(<AppShell><div data-testid="luminous-page">Luminous page</div></AppShell>)

    expect(screen.getByRole('navigation', { name: 'Primary tools' })).toBeInTheDocument()
    expect(screen.getByTestId('luminous-page')).toBeInTheDocument()
    expect(screen.queryByTestId('legacy-sidebar')).toBeNull()
    expect(screen.getByRole('button', { name: 'Enter Focus mode' })).toBeInTheDocument()
  })
})
