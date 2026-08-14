import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NotebookPage from './page'

const { mockUseIsDesktop } = vi.hoisted(() => ({
  mockUseIsDesktop: vi.fn(() => true),
}))

vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'notebook%3Aone' }) }))
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('../components/NotebookHeader', () => ({ NotebookHeader: () => <div>Notebook header</div> }))
vi.mock('../components/SourcesColumn', () => ({ SourcesColumn: () => <div>Sources column</div> }))
vi.mock('../components/NotesColumn', () => ({ NotesColumn: () => <div>Notes column</div> }))
vi.mock('../components/ChatColumn', () => ({ ChatColumn: () => <div>Chat column</div> }))
vi.mock('@/components/research/ResearchRunWorkspace', () => ({ ResearchRunWorkspace: () => <div>Research workspace</div> }))
vi.mock('@/components/deeper-notebook', () => ({ ArtifactRail: () => <div>Artifact rail</div> }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebook: () => ({ data: { id: 'notebook:one', name: 'Field notebook' }, isLoading: false }) }))
vi.mock('@/lib/hooks/use-sources', () => ({ useNotebookSources: () => ({ sources: [], isLoading: false, refetch: vi.fn(), hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }) }))
vi.mock('@/lib/hooks/use-notes', () => ({ useNotes: () => ({ data: [], isLoading: false }) }))
vi.mock('@/lib/stores/notebook-columns-store', () => ({ useNotebookColumnsStore: () => ({ sourcesCollapsed: false, notesCollapsed: false, setSources: vi.fn(), setNotes: vi.fn() }) }))
vi.mock('@/lib/hooks/use-media-query', () => ({ useIsDesktop: mockUseIsDesktop }))
vi.mock('@/components/ui/resizable', () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => ({ 'notebooks.notFound': 'Notebook not found' })[key] ?? key }),
}))

describe('NotebookPage', () => {
  beforeEach(() => {
    mockUseIsDesktop.mockReturnValue(true)
  })

  it('keeps the notebook workspace columns inside an Organize folio', () => {
    render(<NotebookPage />)

    expect(screen.getByRole('main', { name: 'Notebook workspace' })).toBeInTheDocument()
    expect(screen.getByText('Organize')).toBeInTheDocument()
    expect(screen.getByText('Notebook header')).toBeInTheDocument()
    expect(screen.getByText('Sources column')).toBeInTheDocument()
    expect(screen.getByText('Notes column')).toBeInTheDocument()
    expect(screen.getByText('Chat column')).toBeInTheDocument()
  })

  it('mounts one mobile chat column without mounting the CSS-hidden desktop pane', () => {
    mockUseIsDesktop.mockReturnValue(false)

    render(<NotebookPage />)

    expect(screen.getAllByText('Chat column')).toHaveLength(1)
  })
})
