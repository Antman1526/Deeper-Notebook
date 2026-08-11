import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

import { UpdatesCard } from './UpdatesCard'

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))

vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange, ...props }: { checked?: boolean; onCheckedChange?: (value: boolean) => void }) => (
    <input
      {...props}
      type="checkbox"
      checked={checked}
      onChange={(event) => onCheckedChange?.(event.currentTarget.checked)}
    />
  ),
}))

vi.mock('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertTitle: ({ children }: { children: React.ReactNode }) => <strong>{children}</strong>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('lucide-react', () => ({
  RefreshCw: () => null,
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string; [key: string]: unknown }) => {
      let value = options?.defaultValue ?? _key
      for (const [key, replacement] of Object.entries(options ?? {})) {
        if (key !== 'defaultValue') value = value.replace(`{{${key}}}`, String(replacement))
      }
      return value
    },
  }),
}))

let updateData: Record<string, unknown> | undefined
let updateError = false
const mutate = vi.fn()

vi.mock('@/lib/hooks/use-updates', () => ({
  useUpdateCheck: () => ({ data: updateData, isError: updateError }),
  useSetUpdateEnabled: () => ({ mutate, isPending: false }),
  useCheckForUpdatesNow: () => ({ mutate: vi.fn(), isPending: false }),
}))

beforeEach(() => {
  updateData = undefined
  updateError = false
  mutate.mockReset()
})

describe('UpdatesCard verification states', () => {
  it('labels a verified candidate as manual-only and exposes no download control', () => {
    updateData = {
      current: '0.8.69',
      latest: 'v0.8.70',
      update_available: true,
      verification: 'verified',
      enabled: true,
      release_url: 'https://github.com/Antman1526/Deeper-Notebook/releases/tag/v0.8.70',
      last_check: '2026-08-10T00:00:00Z',
    }

    render(<UpdatesCard />)

    expect(screen.getByText('Verified release available (manual review only)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open verified release (manual)' })).toHaveAttribute(
      'href',
      'https://github.com/Antman1526/Deeper-Notebook/releases/tag/v0.8.70',
    )
    expect(screen.queryByText(/download|install/i)).not.toBeInTheDocument()
  })

  it.each([
    ['unverified', 'Release needs verification before it can be offered.'],
    ['unknown', 'Release status unavailable.'],
  ] as const)('renders a safe plain-language state for %s candidates', (verification, message) => {
    updateData = {
      current: '0.8.69',
      latest: 'v0.8.70',
      update_available: true,
      verification,
      enabled: true,
      last_check: '2026-08-10T00:00:00Z',
    }

    render(<UpdatesCard />)

    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByText(/download|install/i)).not.toBeInTheDocument()
  })

  it('renders unavailable language when the check cannot be read and preserves opt-out', () => {
    updateError = true
    updateData = { enabled: false, current: '0.8.69' }

    render(<UpdatesCard />)

    expect(screen.getByText('Release status unavailable.')).toBeInTheDocument()
    expect(screen.queryByText(/download|install/i)).not.toBeInTheDocument()
  })
})
