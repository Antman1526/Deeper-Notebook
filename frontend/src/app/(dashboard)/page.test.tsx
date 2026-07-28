import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import DashboardPage from './page'

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
  it('presents the canonical product name and tagline', () => {
    render(<DashboardPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Think further with every source')).toBeVisible()
  })
})
