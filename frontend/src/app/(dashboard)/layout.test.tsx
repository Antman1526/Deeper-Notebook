import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import DashboardLayout from './layout'

// v0.8.130 — Phase 3b: the shell is mounted once, by this layout. Every page used to
// mount its own, so the rail (and its scroll) reset on each navigation.

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/hooks/use-auth', () => ({ useAuth: () => ({ isAuthenticated: true, isLoading: false }) }))
vi.mock('@/lib/hooks/use-version-check', () => ({ useVersionCheck: () => undefined }))
vi.mock('@/lib/hooks/use-runtime-features', () => ({ useRuntimeFeatures: () => undefined }))
vi.mock('@/components/providers/ModalProvider', () => ({ ModalProvider: () => null }))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  CreateDialogsProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/common/CommandPalette', () => ({ CommandPalette: () => null }))
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div data-testid="app-shell">{children}</div>,
}))

describe('DashboardLayout', () => {
  it('mounts the app shell once, around the page', () => {
    render(<DashboardLayout><p>Page content</p></DashboardLayout>)

    expect(screen.getAllByTestId('app-shell')).toHaveLength(1)
    expect(screen.getByTestId('app-shell')).toHaveTextContent('Page content')
  })
})
