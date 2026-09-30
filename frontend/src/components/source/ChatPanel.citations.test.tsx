import { act, fireEvent, render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'

// T0-5 — citations render inline, inside the sentence they support, as numbered
// chips. The answer used to be split on every marker and each piece rendered as
// its own markdown block, so every pill landed on its own line.

type PillProps = {
  kind: string
  value: string
  label?: string
  onViewSource?: () => void
}
const pillProps: PillProps[] = []
const openModal = vi.hoisted(() => vi.fn())
const chipLifecycle = vi.hoisted(() => ({ mounts: 0, unmounts: 0 }))

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key }),
}))
vi.mock('@/lib/hooks/use-modal-manager', () => ({ useModalManager: () => ({ openModal }) }))
vi.mock('./ModelSelector', () => ({ ModelSelector: () => <div /> }))
vi.mock('@/components/source/SessionManager', () => ({ SessionManager: () => <div /> }))
vi.mock('@/components/source/MessageActions', () => ({ MessageActions: () => <div /> }))
vi.mock('@/components/common/ContextIndicator', () => ({ ContextIndicator: () => <div /> }))
vi.mock('@/components/chat/CitationPill', () => ({
  CitationPill: (props: PillProps) => {
    pillProps.push(props)
    useEffect(() => {
      chipLifecycle.mounts += 1
      return () => { chipLifecycle.unmounts += 1 }
    }, [])
    return (
      <button type="button" data-testid="citation-pill" data-kind={props.kind}>
        {props.label ?? `raw:${props.value}`}
      </button>
    )
  },
}))
vi.mock('@/components/chat/ChatMessageProviderBadge', () => ({ ChatMessageProviderBadge: () => <span /> }))
vi.mock('@/components/chat/ChatMessagePrivacyBadge', () => ({ ChatMessagePrivacyBadge: () => <span /> }))
vi.mock('@/components/chat/ChatMessageAgentStateBadge', () => ({ ChatMessageAgentStateBadge: () => <span /> }))
vi.mock('@/components/chat/McpToolPicker', () => ({ McpToolPicker: () => <div /> }))
vi.mock('@/components/deeper-notebook', () => ({ RunTimeline: () => <div /> }))
vi.mock('@/components/evaluation/EvidenceReview', () => ({ EvidenceReview: () => <span /> }))
vi.mock('@/lib/hooks/use-evaluation', () => ({
  useLatestMessageEvaluations: () => ({ data: {}, isLoading: false, isError: false }),
}))
vi.mock('./SourceDialog', () => ({
  SourceDialog: (props: { sourceId: string | null; highlightQuery?: string }) => (
    <div data-testid="source-dialog" data-source-id={props.sourceId ?? ''} data-query={props.highlightQuery ?? ''} />
  ),
}))

function renderAnswer(content: string) {
  pillProps.length = 0
  return render(
    <ChatPanel
      messages={[{ id: 'message:one', type: 'ai', content }]}
      isStreaming={false}
      contextIndicators={null}
      onSendMessage={vi.fn()}
      notebookId="notebook:one"
      contextType="notebook"
    />,
  )
}

describe('ChatPanel inline citations', () => {
  it('renders each pill inside the paragraph of the sentence it supports', () => {
    const { container } = renderAnswer('Water boils at 100C [source:abc]. Ice melts at 0C [source:def].')

    const pills = screen.getAllByTestId('citation-pill')
    expect(pills).toHaveLength(2)
    // One sentence-pair, one paragraph — not a paragraph per fragment.
    expect(container.querySelectorAll('.prose p')).toHaveLength(1)
    const paragraph = pills[0].closest('p')
    expect(paragraph).not.toBeNull()
    expect(paragraph).toContainElement(pills[1])
    expect(paragraph).toHaveTextContent('Water boils at 100C')
    expect(paragraph).toHaveTextContent('Ice melts at 0C')
  })

  it('keeps separate paragraphs separate, with each pill in its own paragraph', () => {
    const { container } = renderAnswer('First claim [source:a].\n\nSecond claim [source:b].')

    const paragraphs = container.querySelectorAll('.prose p')
    expect(paragraphs).toHaveLength(2)
    expect(paragraphs[0].querySelector('[data-testid="citation-pill"]')).not.toBeNull()
    expect(paragraphs[1].querySelector('[data-testid="citation-pill"]')).not.toBeNull()
  })

  it('numbers citations by first appearance and reuses the number for the same source', () => {
    renderAnswer('A [source:a]. B [note:n]. C [source:a].')
    expect(screen.getAllByTestId('citation-pill').map(pill => pill.textContent)).toEqual(['1', '2', '1'])
  })

  it('leaves MCP tool-call pills on their own index label', () => {
    renderAnswer('Searched the web [mcp:2].')
    const pill = screen.getByTestId('citation-pill')
    expect(pill).toHaveAttribute('data-kind', 'mcp')
    expect(pill).toHaveTextContent('raw:2')
  })

  it('offers "view source" only for source citations', () => {
    renderAnswer('From a source [source:a], a note [note:n] and a tool [mcp:1].')
    const byKind = Object.fromEntries(pillProps.map(props => [props.kind, props]))
    expect(byKind.source.onViewSource).toBeTypeOf('function')
    expect(byKind.note.onViewSource).toBeUndefined()
    expect(byKind.mcp.onViewSource).toBeUndefined()
  })

  it('passes the cited sentence to the source viewer as the passage to highlight', () => {
    renderAnswer('Intro sentence. The moon orbits the Earth [source:moon].')
    const sourcePill = pillProps.find(props => props.kind === 'source')
    act(() => sourcePill?.onViewSource?.())
    const dialog = screen.getByTestId('source-dialog')
    expect(dialog).toHaveAttribute('data-source-id', 'source:moon')
    expect(dialog.getAttribute('data-query')).toBe('The moon orbits the Earth')
  })

  it('keeps legacy reference shapes clickable through the compact-reference converter', () => {
    // `source_insight:ID` is not a chip marker; the older converter numbers it and
    // renders a button that opens the insight modal. The chip work must not break it.
    openModal.mockClear()
    renderAnswer('The finding source_insight:abc123 supports the claim.')

    fireEvent.click(screen.getAllByRole('button', { name: '1' })[0])
    expect(openModal).toHaveBeenCalledWith('insight', 'abc123')
  })

  it('numbers legacy reference links after the chips so no two sources share a number', () => {
    renderAnswer('First [source:a]. Then a legacy reference source_insight:z here.')

    expect(screen.getAllByTestId('citation-pill').map(pill => pill.textContent)).toEqual(['1'])
    // The chip took 1; the legacy reference button must not reuse it.
    const legacyButtons = screen.getAllByRole('button', { name: '2' })
    expect(legacyButtons.length).toBeGreaterThan(0)
    expect(screen.queryAllByRole('button', { name: '1' }).filter(b => b.getAttribute('data-testid') !== 'citation-pill'))
      .toHaveLength(0)
  })

  it('does not remount a chip when the answer grows while streaming', () => {
    chipLifecycle.mounts = 0
    chipLifecycle.unmounts = 0
    const props = {
      isStreaming: true,
      contextIndicators: null,
      onSendMessage: vi.fn(),
      notebookId: 'notebook:one',
      contextType: 'notebook' as const,
    }
    const { rerender } = render(
      <ChatPanel {...props} messages={[{ id: 'streaming-one', type: 'ai', content: 'First claim [source:a].' }]} />,
    )
    expect(chipLifecycle.mounts).toBe(1)

    rerender(
      <ChatPanel
        {...props}
        messages={[{ id: 'streaming-one', type: 'ai', content: 'First claim [source:a]. A second sentence arrives' }]}
      />,
    )
    rerender(
      <ChatPanel
        {...props}
        messages={[{ id: 'streaming-one', type: 'ai', content: 'First claim [source:a]. A second sentence arrives token by token.' }]}
      />,
    )

    // Same chip, same position: React must keep it mounted across streamed tokens.
    expect(chipLifecycle.unmounts).toBe(0)
    expect(chipLifecycle.mounts).toBe(1)
  })

  it('does not turn a marker inside a code span into a citation chip', () => {
    // The older compact-reference converter is not code-aware and is unchanged
    // here; this only guarantees the new chip path leaves code alone.
    renderAnswer('Write `[source:x]` literally, then cite [source:y].')
    const pills = screen.getAllByTestId('citation-pill')
    expect(pills).toHaveLength(1)
    expect(pillProps.map(props => props.value)).toEqual(['y'])
  })
})
