import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CitationPill } from './CitationPill'

// v0.8.130 — numbered citations read as raised footnote markers (two or three
// baseline chips in one sentence broke the prose rhythm), and the popover
// shows the cited passage as a quote with "View source" in a footer row.

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-root' }, children),
  PopoverTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('div', { 'data-testid': 'popover-trigger' }, children),
  PopoverContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-content' }, children),
}))

vi.mock('@/lib/hooks/use-sources', () => ({
  useSource: (id: string) => ({ data: { id, title: 'Source title', full_text: 'Cited source passage.' }, isLoading: false }),
}))
vi.mock('@/lib/hooks/use-notes', () => ({
  useNote: (id: string) => ({ data: { id, title: 'Note title', content: 'Cited note passage.' }, isLoading: false }),
}))
vi.mock('@/lib/hooks/use-insights', () => ({
  useInsight: (id: string) => ({ data: { id, insight_type: 'key_points', content: 'Cited insight passage.' }, isLoading: false }),
}))

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

// text-xs (12px) is the floor: the design lint rejects smaller type (eslint MICRO_TYPE).
const FOOTNOTE = ['align-baseline', '-translate-y-px', 'text-xs', 'leading-4', 'tabular-nums', 'rounded-full', 'font-semibold']

describe('CitationPill — numbered footnote marker', () => {
  it('styles a numbered pill as a compact raised footnote', () => {
    render(<CitationPill kind="source" value="abc" label="1" />, { wrapper })
    const button = screen.getByRole('button', { name: /source abc/ })
    for (const cls of FOOTNOTE) expect(button).toHaveClass(cls)
    expect(button).not.toHaveClass('rounded-sm')
    // Still an inline chip with its focus ring.
    expect(button).toHaveClass('inline-flex', 'focus-visible:ring-2')
  })

  it('leaves un-numbered pills exactly as they were', () => {
    render(<CitationPill kind="source" value="abc12345678" />, { wrapper })
    const button = screen.getByRole('button', { name: /source abc12345678/ })
    expect(button).toHaveClass('text-xs', 'rounded-sm', 'px-1.5', 'py-0')
    expect(button).not.toHaveClass('rounded-full')
    expect(button).not.toHaveClass('-translate-y-px')
  })

  it('leaves mcp [N] pills exactly as they were', () => {
    render(<CitationPill kind="mcp" value="2" />, { wrapper })
    const button = screen.getByRole('button')
    expect(button).toHaveTextContent('[2]')
    expect(button).toHaveClass('text-xs', 'rounded-sm')
  })
})

describe('CitationPill — popover passage and footer', () => {
  it.each([
    ['source', 'Cited source passage.'],
    ['note', 'Cited note passage.'],
    ['insight', 'Cited insight passage.'],
  ] as const)('renders the %s excerpt as a clamped quoted passage', (kind, text) => {
    render(<CitationPill kind={kind} value="x1" label="1" />, { wrapper })
    const passage = screen.getByText(text)
    expect(passage.tagName).toBe('BLOCKQUOTE')
    expect(passage).toHaveClass('border-l-2', 'border-primary/40', 'pl-2.5', 'italic', 'text-foreground/85', 'bg-muted/30', 'py-1', 'rounded-r-sm', 'line-clamp-3')
  })

  it('puts "View source" in a hairline-separated footer row and keeps its behaviour', () => {
    const onViewSource = vi.fn()
    render(<CitationPill kind="source" value="s1" label="1" onViewSource={onViewSource} />, { wrapper })
    const action = screen.getByRole('button', { name: /chat\.citations\.viewSource|View source/ })
    const footer = action.parentElement!
    expect(footer).toHaveClass('border-t', 'border-border/60', 'pt-2', 'mt-2', 'flex', 'justify-end')
    fireEvent.click(action)
    expect(onViewSource).toHaveBeenCalledTimes(1)
  })

  it('renders no footer without onViewSource', () => {
    const { container } = render(<CitationPill kind="source" value="s1" label="1" />, { wrapper })
    expect(container.querySelector('.border-t')).toBeNull()
  })
})
