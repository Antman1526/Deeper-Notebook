import { act, fireEvent, render, screen } from '@testing-library/react'
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
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
  useSourceVisualsEnabled: mockSourceVisualsEnabled,
}))

vi.mock('@/components/sources/SourceCard', () => ({
  SourceCard: (props: {
    source: { id: string; title: string }
    showVisualCover?: boolean
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
vi.mock('./BulkVectorizeButton', () => ({ BulkVectorizeButton: () => null }))
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
})
