import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DashboardPage from './page'

const routerPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    header: ({ children }: { children: React.ReactNode }) => (
      <header>{children}</header>
    ),
  },
  useReducedMotion: () => true,
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}))

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/lib/hooks/use-system-status', () => ({
  useSystemStatus: () => ({ data: undefined }),
}))

describe('DashboardPage active product identity', () => {
  afterEach(() => {
    routerPush.mockClear()
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO
  })

  it('presents the canonical product name and tagline', () => {
    render(<DashboardPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Think further with every source')).toBeVisible()
  })

  it.each(['0', '1'])('keeps the Horizon presentation compatible with shell flag %s', (flag) => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = flag
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('href', '/search')
  })

  it('keeps route navigation in the page callback wiring', () => {
    render(<DashboardPage />)

    fireEvent.click(screen.getByRole('link', { name: 'Studio' }))
    fireEvent.click(screen.getByRole('link', { name: 'Ask' }))

    expect(routerPush).toHaveBeenNthCalledWith(1, '/studio')
    expect(routerPush).toHaveBeenNthCalledWith(2, '/search')
  })
})
