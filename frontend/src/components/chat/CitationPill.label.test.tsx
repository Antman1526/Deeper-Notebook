import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CitationPill } from './CitationPill'

// T0-5 — the pill used to print an ID fragment ("so:abc12345"). Callers that
// number their citations pass `label` so the pill reads like a footnote marker.
// Without `label` the legacy text is kept (see CitationPill.test.tsx).

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-root' }, children),
  PopoverTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('div', { 'data-testid': 'popover-trigger' }, children),
  PopoverContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-content' }, children),
}))

vi.mock('@/lib/hooks/use-sources', () => ({
  useSource: (id: string) => ({ data: { id, title: 'Test Source Title', full_text: 'Excerpt.' }, isLoading: false }),
}))
vi.mock('@/lib/hooks/use-notes', () => ({
  useNote: (id: string) => ({ data: { id, title: 'Test Note Title', content: 'Note.' }, isLoading: false }),
}))
vi.mock('@/lib/hooks/use-insights', () => ({
  useInsight: (id: string) => ({ data: { id, insight_type: 'key_points', content: 'Insight.' }, isLoading: false }),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

describe('CitationPill label', () => {
  it('shows the supplied label instead of an ID fragment', () => {
    render(<CitationPill kind="source" value="abc12345678xyz" label="2" />, { wrapper })
    const button = screen.getByRole('button')
    expect(button).toHaveTextContent(/^2$/)
    expect(button).not.toHaveTextContent('so:abc12345')
  })

  it('still identifies the cited record to assistive tech when the label is only a number', () => {
    render(<CitationPill kind="note" value="n42" label="3" />, { wrapper })
    expect(screen.getByRole('button')).toHaveAccessibleName(/note/i)
  })

  it('keeps the inline-flex chip layout so it can sit inside a paragraph', () => {
    render(<CitationPill kind="source" value="abc" label="1" />, { wrapper })
    expect(screen.getByRole('button').className).toContain('inline-flex')
  })
})
