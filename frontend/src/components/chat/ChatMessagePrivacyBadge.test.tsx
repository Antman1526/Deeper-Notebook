import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatMessagePrivacyBadge } from './ChatMessagePrivacyBadge'

// v0.8.61 / v0.8.63 — tests for the "On-device" privacy review popover.

// Popover stub renders trigger + content inline (no open-state gating in JSDOM).
vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-root' }, children),
  PopoverTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('span', null, children),
  PopoverContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-content' }, children),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _k
      let s = opts.defaultValue ?? _k
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

function renderWithClient(ui: React.ReactNode, prepopulate?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (prepopulate) prepopulate(qc)
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const gated = (qc: QueryClient, id: string, cats: string[]) =>
  qc.setQueryData(['chat', 'selected-provider', id], {
    privacy_gated: true,
    privacy_categories: cats,
  })

describe('ChatMessagePrivacyBadge', () => {
  it('renders the badge + lists categories in the review popover', () => {
    renderWithClient(<ChatMessagePrivacyBadge messageId="m:1" />, qc =>
      gated(qc, 'm:1', ['email', 'person_name']),
    )
    expect(screen.getByTestId('privacy-badge')).toBeInTheDocument()
    const content = screen.getByTestId('popover-content').textContent
    expect(content).toContain('email')
    expect(content).toContain('person_name')
  })

  it('shows the "Re-ask allowing cloud" button and calls onReask when provided', () => {
    const onReask = vi.fn()
    renderWithClient(
      <ChatMessagePrivacyBadge messageId="m:2" onReask={onReask} />,
      qc => gated(qc, 'm:2', ['email']),
    )
    const btn = screen.getByTestId('privacy-reask')
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onReask).toHaveBeenCalledTimes(1)
  })

  it('omits the re-ask button when no onReask is provided (review-only)', () => {
    renderWithClient(<ChatMessagePrivacyBadge messageId="m:3" />, qc =>
      gated(qc, 'm:3', ['email']),
    )
    expect(screen.queryByTestId('privacy-reask')).toBeNull()
  })

  it('renders nothing when privacy_gated is false/absent', () => {
    const { container } = renderWithClient(
      <ChatMessagePrivacyBadge messageId="m:4" />,
      qc =>
        qc.setQueryData(['chat', 'selected-provider', 'm:4'], { privacy_gated: false }),
    )
    expect(container.textContent).toBe('')
  })

  it('renders nothing when there is no cache entry', () => {
    const { container } = renderWithClient(<ChatMessagePrivacyBadge messageId="m:none" />)
    expect(container.textContent).toBe('')
  })
})
