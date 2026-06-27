import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

import { UpdateBanner } from './UpdateBanner'

// v0.8.70 — banner is a thin shell over useUpdateCheck. Assert the visibility
// rules (available / skipped / no-update) and that Skip fires with the version.

vi.mock('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert' }, children),
  AlertTitle: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-title' }, children),
  AlertDescription: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-desc' }, children),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, asChild }: { children: React.ReactNode; onClick?: () => void; asChild?: boolean }) =>
    asChild
      ? React.createElement('span', {}, children)
      : React.createElement('button', { onClick }, children),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _key
      let s = opts.defaultValue ?? _key
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

const skipMutate = vi.fn()
let updateData: Record<string, unknown> | undefined

vi.mock('@/lib/hooks/use-updates', () => ({
  useUpdateCheck: () => ({ data: updateData }),
  useSkipVersion: () => ({ mutate: skipMutate, isPending: false }),
}))

beforeEach(() => {
  skipMutate.mockReset()
  updateData = undefined
})

describe('UpdateBanner', () => {
  it('renders nothing when there is no update', () => {
    updateData = { current: '0.8.69', update_available: false, skipped: false }
    const { container } = render(<UpdateBanner />)
    expect(container.textContent).toBe('')
  })

  it('renders nothing when the available version was skipped', () => {
    updateData = {
      current: '0.8.69',
      latest: 'v0.8.70',
      update_available: true,
      skipped: true,
      html_url: 'https://x/releases/v0.8.70',
    }
    const { container } = render(<UpdateBanner />)
    expect(container.textContent).toBe('')
  })

  it('shows the banner with version and download link when an update is available', () => {
    updateData = {
      current: '0.8.69',
      latest: 'v0.8.70',
      update_available: true,
      skipped: false,
      html_url: 'https://x/releases/v0.8.70',
    }
    render(<UpdateBanner />)
    expect(screen.getByTestId('alert-title').textContent).toContain('v0.8.70')
    const link = screen.getByText('Download').closest('a')
    expect(link).toHaveAttribute('href', 'https://x/releases/v0.8.70')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })

  it('Skip this version fires the mutation with the latest version', () => {
    updateData = {
      current: '0.8.69',
      latest: 'v0.8.70',
      update_available: true,
      skipped: false,
      html_url: 'https://x/releases/v0.8.70',
    }
    render(<UpdateBanner />)
    screen.getByText('Skip this version').click()
    expect(skipMutate).toHaveBeenCalledWith('v0.8.70')
  })
})
