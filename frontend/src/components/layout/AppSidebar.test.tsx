/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AppSidebar, getNavigation } from './AppSidebar'
import { useSidebarStore } from '@/lib/stores/sidebar-store'

// v0.8.0 — mock the LocalModelHealthBadges component so the
// AppSidebar tests don't need a QueryClientProvider. The badge
// component has its own dedicated test suite.
vi.mock('@/components/chat/LocalModelHealthBadges', () => ({
  LocalModelHealthBadges: () => null,
}))

// Mock Tooltip components to avoid Radix UI async issues in tests
vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

// v0.7.41 — force desktop viewport for these tests. The new
// useIsDesktop() returns false under jsdom by default (SSR-safe), which
// would force the sidebar into collapsed mode regardless of the store
// state. These tests are about sidebar BEHAVIOR, not media-query
// behavior — mock the hook to always say "yes, you're on desktop".
vi.mock('@/lib/hooks/use-media-query', () => ({
  useMediaQuery: () => true,
  useIsDesktop: () => true,
}))

describe('AppSidebar', () => {
  it('offers the translated Study destination in the sidebar navigation', () => {
    const translate = (key: string) => ({
      'navigation.study': 'Study',
    }[key] ?? key)

    const navigation = getNavigation(translate as never) as ReadonlyArray<{
      items: ReadonlyArray<{ href: string; name: string }>
    }>
    expect(navigation
      .flatMap(section => section.items)
      .some(item => item.href === '/study' && item.name === 'Study'))
      .toBe(true)
  })

  it('renders correctly when expanded', () => {
    render(<AppSidebar />)

    // With mocked t() returning keys, check for translation key strings
    expect(screen.getByText('common.appName')).toBeDefined()
    expect(screen.getByText('navigation.sources')).toBeDefined()
    expect(screen.getByText('navigation.notebooks')).toBeDefined()
    expect(screen.getByText('navigation.knowledge')).toBeDefined()
  })

  it('toggles collapse state when clicking handle', () => {
    const toggleCollapse = vi.fn()
    vi.mocked(useSidebarStore).mockReturnValue({
      isCollapsed: false,
      toggleCollapse,
    } as any)

    render(<AppSidebar />)

    fireEvent.click(screen.getByTestId('sidebar-toggle'))

    expect(toggleCollapse).toHaveBeenCalled()
  })

  it('shows collapsed view when isCollapsed is true', () => {
    vi.mocked(useSidebarStore).mockReturnValue({
      isCollapsed: true,
      toggleCollapse: vi.fn(),
    } as any)

    render(<AppSidebar />)

    // In collapsed mode, app name shouldn't be visible (as text)
    expect(screen.queryByText('common.appName')).toBeNull()
    expect(
      screen.getByRole('img', { name: 'Deeper Notebook' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch theme' })).toHaveClass('h-9', 'w-full')
    expect(screen.getByRole('button', { name: 'navigation.language' })).toHaveClass('h-9', 'w-full')
  })
})
