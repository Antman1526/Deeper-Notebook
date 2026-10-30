import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SourcesColumn } from './SourcesColumn'

const {
  mockVisualSystemEnabled,
  mockSourceVisualsEnabled,
  mockSourceCard,
  mockVirtualizedList,
  mockFetchNextPage,
  mockOpenModal,
  mockDeleteMutateAsync,
  mockRetryMutateAsync,
  mockRemoveMutateAsync,
  mockAddSourceDialog,
  mockBulkVectorize,
} = vi.hoisted(() => ({
  mockVisualSystemEnabled: vi.fn(() => false),
  mockSourceVisualsEnabled: vi.fn(() => false),
  mockSourceCard: vi.fn(),
  mockVirtualizedList: vi.fn(),
  mockFetchNextPage: vi.fn(),
  mockOpenModal: vi.fn(),
  mockDeleteMutateAsync: vi.fn().mockResolvedValue(undefined),
  mockRetryMutateAsync: vi.fn().mockResolvedValue(undefined),
  mockRemoveMutateAsync: vi.fn().mockResolvedValue(undefined),
  mockAddSourceDialog: vi.fn(),
  mockBulkVectorize: vi.fn(),
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
}))
vi.mock('@/lib/features-client', () => ({ useSourceVisualsEnabled: mockSourceVisualsEnabled }))

vi.mock('@/components/sources/SourceCard', () => ({
  SourceCard: (props: {
    source: { id: string; title: string }
    showVisualCover?: boolean
    active?: boolean
    onClick?: (id: string) => void
    onDelete?: (id: string) => void
    onRetry?: (id: string) => void
    onRemoveFromNotebook?: (id: string) => void
    onContextModeChange?: (mode: 'full' | 'insights' | 'exclude') => void
  }) => {
    mockSourceCard(props)
    return (
      <button
        type="button"
        data-cover={String(props.showVisualCover)}
        data-active={props.active ? 'true' : undefined}
        onClick={() => props.onClick?.(props.source.id)}
      >
        {props.source.title}
      </button>
    )
  },
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
    <div data-testid="sources-drop-zone" {...props}>{children}</div>
  ),
  CardContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/common/LoadingSpinner', () => ({ LoadingSpinner: () => <div>Loading</div> }))
vi.mock('@/components/common/EmptyState', () => ({ EmptyState: () => <div>Empty</div> }))
vi.mock('@/components/sources/AddSourceDialog', () => ({
  AddSourceDialog: (props: unknown) => {
    mockAddSourceDialog(props)
    return null
  },
}))
vi.mock('@/components/sources/AddExistingSourceDialog', () => ({ AddExistingSourceDialog: () => null }))
vi.mock('@/components/sources/DiscoverSourcesDialog', () => ({ DiscoverSourcesDialog: () => null }))
vi.mock('@/components/source/SourceDetailContent', () => ({
  SourceDetailContent: ({ sourceId, highlightQuery }: { sourceId: string; highlightQuery?: string }) => (
    <div data-testid="source-detail-content" data-source-id={sourceId} data-query={highlightQuery ?? ''} />
  ),
}))
vi.mock('@/components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({ open, title, onConfirm }: { open: boolean; title: string; onConfirm: () => void }) => (
    open ? <button type="button" onClick={onConfirm}>{title}</button> : null
  ),
}))
vi.mock('@/components/notebooks/CollapsibleColumn', () => ({
  CollapsibleColumn: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  createCollapseButton: () => null,
}))
vi.mock('@/components/ui/virtualized-list', () => ({
  VirtualizedListAuto: (props: {
    items: Array<{ id: string; title: string }>
    renderItem: (item: { id: string; title: string }) => React.ReactNode
    onScroll: (event: React.UIEvent<HTMLDivElement>) => void
  }) => {
    mockVirtualizedList(props)
    return <div data-testid="virtualized">{props.renderItem(props.items[0])}</div>
  },
}))
vi.mock('./BulkVectorizeButton', () => ({
  BulkVectorizeButton: (props: { open?: boolean; hideTrigger?: boolean }) => {
    mockBulkVectorize(props)
    return null
  },
}))
vi.mock('@/lib/hooks/use-sources', () => ({
  useDeleteSource: () => ({ mutateAsync: mockDeleteMutateAsync, isPending: false }),
  useRetrySource: () => ({ mutateAsync: mockRetryMutateAsync }),
  useRemoveSourceFromNotebook: () => ({ mutateAsync: mockRemoveMutateAsync, isPending: false }),
}))
vi.mock('@/lib/hooks/use-modal-manager', () => ({ useModalManager: () => ({ openModal: mockOpenModal }) }))
vi.mock('@/lib/stores/notebook-columns-store', () => ({ useNotebookColumnsStore: () => ({ sourcesCollapsed: false, toggleSources: vi.fn() }) }))
vi.mock('@/lib/hooks/use-translation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

const source = {
  id: 'source:one',
  title: 'Field notes',
  asset: null,
  embedded: true,
  embedded_chunks: 1,
  insights_count: 0,
  created: '2026-08-10T00:00:00Z',
  updated: '2026-08-10T00:00:00Z',
}

function firstCardProps() {
  return mockSourceCard.mock.calls[0]?.[0] as {
    source: typeof source
    showVisualCover?: boolean
    contextMode?: 'full' | 'insights' | 'exclude'
    onClick?: (id: string) => void
    onDelete?: (id: string) => void
    onRetry?: (id: string) => void
    onRemoveFromNotebook?: (id: string) => void
    onContextModeChange?: (mode: 'full' | 'insights' | 'exclude') => void
  }
}

describe('SourcesColumn visual rollback gate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockVisualSystemEnabled.mockReturnValue(false)
    mockSourceVisualsEnabled.mockReturnValue(false)
  })

  it('adds the compact cover flag while preserving normal-card selection, context, and action callbacks', async () => {
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    const onRefresh = vi.fn()
    const onContextModeChange = vi.fn()

    render(
      <SourcesColumn
        sources={[source]}
        isLoading={false}
        notebookId="notebook:one"
        onRefresh={onRefresh}
        contextSelections={{ [source.id]: 'full' }}
        onContextModeChange={onContextModeChange}
      />
    )

    const props = firstCardProps()
    expect(props).toEqual(expect.objectContaining({ showVisualCover: true, contextMode: 'full' }))
    props.onClick?.(source.id)
    expect(mockOpenModal).toHaveBeenCalledWith('source', source.id)
    props.onContextModeChange?.('insights')
    expect(onContextModeChange).toHaveBeenCalledWith(source.id, 'insights')
    await act(async () => {
      props.onDelete?.(source.id)
    })
    fireEvent.click(screen.getByRole('button', { name: 'sources.delete' }))
    await vi.waitFor(() => expect(mockDeleteMutateAsync).toHaveBeenCalledWith(source.id))
    expect(onRefresh).toHaveBeenCalledOnce()
    props.onRetry?.(source.id)
    await vi.waitFor(() => expect(mockRetryMutateAsync).toHaveBeenCalledWith(source.id))
    await act(async () => {
      props.onRemoveFromNotebook?.(source.id)
    })
    fireEvent.click(screen.getByRole('button', { name: 'sources.removeFromNotebook' }))
    await vi.waitFor(() => expect(mockRemoveMutateAsync).toHaveBeenCalledWith({ notebookId: 'notebook:one', sourceId: source.id }))
  })

  it.each([
    ['V2 off / source visuals on', false, true],
    ['V2 on / source visuals off', true, false],
  ])('keeps compact covers off when %s', (_label, visualSystemEnabled, sourceVisualsEnabled) => {
    mockVisualSystemEnabled.mockReturnValue(visualSystemEnabled)
    mockSourceVisualsEnabled.mockReturnValue(sourceVisualsEnabled)

    render(<SourcesColumn sources={[source]} isLoading={false} notebookId="notebook:one" />)

    expect(firstCardProps()).toEqual(expect.objectContaining({ showVisualCover: false }))
  })

  it('keeps the exact 49/50 virtualization boundary and infinite-scroll threshold', () => {
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    const fortyNineSources = Array.from({ length: 49 }, (_, index) => ({ ...source, id: `source:${index}`, title: `Source ${index}` }))
    const fiftySources = Array.from({ length: 50 }, (_, index) => ({ ...source, id: `source:${index}`, title: `Source ${index}` }))
    const { rerender } = render(
      <SourcesColumn sources={fortyNineSources} isLoading={false} notebookId="notebook:one" hasNextPage fetchNextPage={mockFetchNextPage} />
    )

    expect(screen.queryByTestId('virtualized')).not.toBeInTheDocument()
    expect(firstCardProps()).toEqual(expect.objectContaining({ showVisualCover: true }))
    vi.clearAllMocks()
    rerender(
      <SourcesColumn sources={fiftySources} isLoading={false} notebookId="notebook:one" hasNextPage fetchNextPage={mockFetchNextPage} />
    )

    expect(screen.getByTestId('virtualized')).toBeInTheDocument()
    const virtualizedProps = mockVirtualizedList.mock.calls[0]?.[0] as {
      onScroll: (event: React.UIEvent<HTMLDivElement>) => void
    }
    virtualizedProps.onScroll({ currentTarget: { scrollTop: 600, scrollHeight: 1000, clientHeight: 200 } } as React.UIEvent<HTMLDivElement>)
    expect(mockFetchNextPage).not.toHaveBeenCalled()
    virtualizedProps.onScroll({ currentTarget: { scrollTop: 601, scrollHeight: 1000, clientHeight: 200 } } as React.UIEvent<HTMLDivElement>)
    expect(mockFetchNextPage).toHaveBeenCalledOnce()
  })

  it('keeps drag-and-drop source prefill intact', () => {
    const file = new File(['notes'], 'notes.pdf', { type: 'application/pdf' })
    render(<SourcesColumn sources={[source]} isLoading={false} notebookId="notebook:one" />)

    fireEvent.drop(screen.getByTestId('sources-drop-zone'), {
      dataTransfer: { types: ['Files'], files: [file] },
    })

    expect(mockAddSourceDialog).toHaveBeenLastCalledWith(expect.objectContaining({
      open: true,
      defaultNotebookId: 'notebook:one',
      initialFiles: [file],
    }))
  })

  // v0.8.130 — Phase 2b: bulk context and Embed all share one "Source options" menu so the
  // header keeps a single row of 44px targets in a 20% column.
  it('groups bulk context and embed-all under one Source options menu', () => {
    const onBulkContextModeChange = vi.fn()
    render(
      <SourcesColumn
        sources={[source]}
        isLoading={false}
        notebookId="notebook:one"
        onBulkContextModeChange={onBulkContextModeChange}
      />
    )

    expect(screen.getByRole('button', { name: 'sources.sourceOptions' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'sources.bulkContext' })).not.toBeInTheDocument()
    expect(mockBulkVectorize).toHaveBeenLastCalledWith(expect.objectContaining({ open: false, hideTrigger: true }))

    fireEvent.click(screen.getByRole('button', { name: 'sources.includeAllFull' }))
    expect(onBulkContextModeChange).toHaveBeenCalledWith('full')

    fireEvent.click(screen.getByRole('button', { name: 'notebooks.bulkVectorize.button' }))
    expect(mockBulkVectorize).toHaveBeenLastCalledWith(expect.objectContaining({ open: true, hideTrigger: true }))
  })

  // v0.8.130 — the source last opened stays marked in the list (until another is opened),
  // so the reader's place in the list survives going back.
  it('marks only the most recently opened source as active', () => {
    const second = { ...source, id: 'source:two', title: 'Lab report' }
    render(<SourcesColumn sources={[source, second]} isLoading={false} notebookId="notebook:one" />)

    const first = screen.getByRole('button', { name: 'Field notes' })
    const other = screen.getByRole('button', { name: 'Lab report' })
    expect(first).not.toHaveAttribute('data-active')
    expect(other).not.toHaveAttribute('data-active')

    fireEvent.click(first)
    expect(mockOpenModal).toHaveBeenCalledWith('source', source.id)
    expect(screen.getByRole('button', { name: 'Field notes' })).toHaveAttribute('data-active', 'true')
    expect(screen.getByRole('button', { name: 'Lab report' })).not.toHaveAttribute('data-active')

    fireEvent.click(screen.getByRole('button', { name: 'Lab report' }))
    expect(screen.getByRole('button', { name: 'Field notes' })).not.toHaveAttribute('data-active')
    expect(screen.getByRole('button', { name: 'Lab report' })).toHaveAttribute('data-active', 'true')
  })

  it('opens the inline source reader on dn:preview-source and returns to the list', () => {
    render(<SourcesColumn sources={[source]} isLoading={false} notebookId="notebook:one" />)

    act(() => {
      window.dispatchEvent(new CustomEvent('dn:preview-source', {
        detail: { sourceId: 'source:one', highlightQuery: 'key passage' },
      }))
    })

    expect(screen.getByTestId('inline-source-reader')).toBeInTheDocument()
    const detail = screen.getByTestId('source-detail-content')
    expect(detail).toHaveAttribute('data-source-id', 'source:one')
    expect(detail).toHaveAttribute('data-query', 'key passage')

    fireEvent.click(screen.getByRole('button', { name: 'navigation.sources' }))
    expect(screen.queryByTestId('inline-source-reader')).not.toBeInTheDocument()
  })

  it('opens inline reader on card click when inlineReader is enabled and closes on Escape', () => {
    render(<SourcesColumn sources={[source]} isLoading={false} notebookId="notebook:one" inlineReader />)

    const props = firstCardProps()
    act(() => {
      props.onClick?.(source.id)
    })

    expect(mockOpenModal).not.toHaveBeenCalled()
    expect(screen.getByTestId('inline-source-reader')).toBeInTheDocument()

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(screen.queryByTestId('inline-source-reader')).not.toBeInTheDocument()
  })
})

// v0.8.130 — user request 2026-10-29: the reader's bar ("← Sources", open in a window)
// scrolled away with a long source. It stays at the top of the column and names the
// source being read, so the way back and the context are always in view.
describe('SourcesColumn inline reader bar', () => {
  it('stays at the top of the column and names the source being read', () => {
    render(<SourcesColumn sources={[source]} isLoading={false} notebookId="notebook:one" inlineReader />)
    act(() => {
      window.dispatchEvent(new CustomEvent('dn:preview-source', { detail: { sourceId: source.id } }))
    })

    const bar = screen.getByTestId('inline-source-reader-bar')
    expect(bar.className).toMatch(/\bsticky\b/)
    // Pinned to the column's top edge, not its padding edge (text showed above it).
    expect(bar.className).toMatch(/-top-3\b/)
    expect(bar.className).toMatch(/\bbg-card\b/)
    expect(bar.className).not.toMatch(/backdrop-blur/)
    const title = within(bar).getByText(source.title as string)
    expect(title.className).toMatch(/\btruncate\b/)
    expect(title).toHaveAttribute('title', source.title)
    expect(within(bar).getByRole('button', { name: 'navigation.sources' })).toBeInTheDocument()
    expect(within(bar).getByRole('button', { name: 'sources.detailsTitle' })).toBeInTheDocument()
  })
})

// v0.8.130 — the reader's text was about three words a line: inside the column it sat in
// a bordered card with 24px padding each side. The reader marks itself so the card's frame
// can go there (the dialog keeps it), and it announces when it opens and closes so the
// workspace can widen the column while reading.
describe('SourcesColumn inline reader width', () => {
  it('marks the reader and announces opening and closing', () => {
    const events: Array<boolean | undefined> = []
    const listener = (event: Event) => events.push((event as CustomEvent<{ open?: boolean }>).detail?.open)
    window.addEventListener('dn:inline-reader', listener)
    try {
      render(<SourcesColumn sources={[source]} isLoading={false} notebookId="notebook:one" inlineReader />)
      act(() => {
        window.dispatchEvent(new CustomEvent('dn:preview-source', { cancelable: true, detail: { sourceId: source.id } }))
      })
      expect(screen.getByTestId('inline-source-reader')).toHaveAttribute('data-dn-inline-reader')
      fireEvent.click(screen.getByRole('button', { name: 'navigation.sources' }))
      expect(events).toEqual([true, false])
    } finally {
      window.removeEventListener('dn:inline-reader', listener)
    }
  })
})
