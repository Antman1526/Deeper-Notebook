import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CitationPill } from './CitationPill'

// v0.8.0 Phase 4 Task 14 — component tests for CitationPill.

// Mock Radix Popover so popover content is always rendered in JSDOM.
// Radix uses a Portal + CSS animation; in JSDOM the Portal destination exists
// but the animation state gate prevents content from appearing. We swap the
// three Radix pieces for simple semantic wrappers that always show content.
vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-root' }, children),
  PopoverTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('div', { 'data-testid': 'popover-trigger' }, children),
  PopoverContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-content' }, children),
}))

// Mocks for the lazy-fetch hooks used in popover bodies.
vi.mock('@/lib/hooks/use-sources', () => ({
  useSource: (id: string) => ({
    data: {
      id,
      title: 'Test Source Title',
      full_text: 'Some source text excerpt for the popover.',
    },
    isLoading: false,
  }),
}))

vi.mock('@/lib/hooks/use-notes', () => ({
  useNote: (id: string) => ({
    data: {
      id,
      title: 'Test Note Title',
      content: 'Some note content for the popover.',
      note_type: null,
    },
    isLoading: false,
  }),
}))

function makeWrapper() {
  const qc = new QueryClient()
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'TestWrapper'
  return Wrapper
}

describe('CitationPill', () => {
  it('renders an mcp pill with the correct label', () => {
    render(<CitationPill kind="mcp" value="1" />, {
      wrapper: makeWrapper(),
    })
    // MCP pill shows [1]
    expect(screen.getByRole('button')).toBeInTheDocument()
    expect(screen.getByRole('button')).toHaveTextContent('[1]')
  })

  it('renders a source pill with the correct abbreviated label', () => {
    render(<CitationPill kind="source" value="abc12345678xyz" />, {
      wrapper: makeWrapper(),
    })
    // Source pill shows "so:abc12345" (first 8 chars of value)
    expect(screen.getByRole('button')).toHaveTextContent('so:abc12345')
  })

  it('mcp pill is focusable and keyboard-accessible', () => {
    render(<CitationPill kind="mcp" value="2" />, {
      wrapper: makeWrapper(),
    })
    const btn = screen.getByRole('button')
    btn.focus()
    expect(btn).toHaveFocus()
  })

  it('mcp pill popover content shows tool-call label and placeholder text', () => {
    // The Popover is mocked to always render its content, so no click needed.
    render(<CitationPill kind="mcp" value="1" />, {
      wrapper: makeWrapper(),
    })

    // The mock t() returns the i18n key, so check for the key string
    expect(screen.getByText(/chat\.citations\.toolCallLabel/)).toBeInTheDocument()
    expect(screen.getByText(/chat\.citations\.mcpPlaceholder/)).toBeInTheDocument()
  })

  it('source pill popover content shows source label and source data', () => {
    render(<CitationPill kind="source" value="testSourceId" />, {
      wrapper: makeWrapper(),
    })

    expect(screen.getByText(/chat\.citations\.sourceLabel/)).toBeInTheDocument()
    expect(screen.getByText('Test Source Title')).toBeInTheDocument()
  })

  it('note pill popover content shows note label and note data', () => {
    render(<CitationPill kind="note" value="testNoteId" />, {
      wrapper: makeWrapper(),
    })

    expect(screen.getByText(/chat\.citations\.noteLabel/)).toBeInTheDocument()
    expect(screen.getByText('Test Note Title')).toBeInTheDocument()
  })

  it('renders insight pill without errors', () => {
    const { container } = render(<CitationPill kind="insight" value="ins123" />, {
      wrapper: makeWrapper(),
    })
    expect(container.querySelector('button')).not.toBeNull()
  })
})
