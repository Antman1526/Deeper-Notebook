import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CitationPill } from './CitationPill'
import type { McpToolCall } from '@/lib/types/api'

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

// v0.8.1 Item 4 — insight pill now uses useInsight (not useSource).
// Mock returns enough shape for the popover to render the title.
vi.mock('@/lib/hooks/use-insights', () => ({
  useInsight: (id: string) => ({
    data: {
      id,
      source_id: 'source:parent_xyz',
      insight_type: 'key_points',
      content: 'Generated insight content for the popover.',
      created: '2026-05-25T10:00:00Z',
      updated: '2026-05-25T10:00:00Z',
    },
    isLoading: false,
  }),
}))

function makeWrapper(queryClient?: QueryClient) {
  const qc = queryClient ?? new QueryClient()
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

  it('insight pill popover shows insight_type + content excerpt (v0.8.1 useInsight wire-up)', () => {
    // v0.8.1 Item 4 — guards against regressing to useSource(id) which
    // would silently 404 and show the italic fallback. Asserts on
    // insight_type (humanized) + content excerpt — SourceInsightResponse
    // has no `title` field.
    render(<CitationPill kind="insight" value="source_insight:xyz" />, {
      wrapper: makeWrapper(),
    })

    expect(screen.getByText(/chat\.citations\.insightLabel/)).toBeInTheDocument()
    // insight_type 'key_points' → 'key points' after underscore strip + capitalize CSS
    expect(screen.getByText(/key points/i)).toBeInTheDocument()
    expect(screen.getByText(/Generated insight content/)).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // v0.8.1 Item 3 — MCP pill payload rendering from TanStack Query cache
  // ---------------------------------------------------------------------------

  it('mcp pill popover renders tool name, args, and result when cache is populated', () => {
    // Pre-populate the TanStack Query cache with a fake MCP tool-call payload
    // keyed by the message id we'll pass as messageId prop.
    const qc = new QueryClient()
    const calls: McpToolCall[] = [
      {
        index: 1,
        name: 'web_search',
        args: { query: 'open notebook plus features' },
        text: 'Open notebook+ is a desktop research app.',
      },
    ]
    qc.setQueryData(['mcp', 'tool-calls', 'msg-test-123'], calls)

    render(
      <CitationPill kind="mcp" value="1" messageId="msg-test-123" />,
      { wrapper: makeWrapper(qc) },
    )

    // Tool name label
    expect(screen.getByText(/chat\.citations\.mcpToolName/)).toBeInTheDocument()
    // Tool function name
    expect(screen.getByText(/web_search/)).toBeInTheDocument()
    // Args section header
    expect(screen.getByText(/chat\.citations\.mcpArgs/)).toBeInTheDocument()
    // Args JSON includes the query
    expect(screen.getByText(/open notebook plus features/)).toBeInTheDocument()
    // Result section
    expect(screen.getByText(/chat\.citations\.mcpResult/)).toBeInTheDocument()
    // Result excerpt ('+' escaped — it's a regex metacharacter in the brand name)
    expect(screen.getByText(/Open notebook\+ is a desktop/)).toBeInTheDocument()
  })

  it('mcp pill popover falls back to placeholder when no cached payload exists', () => {
    // No cache entry set — should show the updated placeholder.
    render(
      <CitationPill kind="mcp" value="1" messageId="msg-no-cache" />,
      { wrapper: makeWrapper() },
    )

    expect(screen.getByText(/chat\.citations\.toolCallLabel/)).toBeInTheDocument()
    // v0.8.1 Item 3 — placeholder is now the "older session" fallback message
    expect(screen.getByText(/chat\.citations\.mcpPlaceholder/)).toBeInTheDocument()
    // Must NOT show the tool-name label (that only appears when payload found)
    expect(screen.queryByText(/chat\.citations\.mcpToolName/)).not.toBeInTheDocument()
  })
})
