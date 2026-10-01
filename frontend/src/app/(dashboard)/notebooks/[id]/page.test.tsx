import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NotebookPage from './page'

const { mockUseIsDesktop, mockUseIsWideDesktop, chatMounts } = vi.hoisted(() => ({
  mockUseIsDesktop: vi.fn(() => true),
  mockUseIsWideDesktop: vi.fn(() => true),
  chatMounts: { count: 0 },
}))

vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'notebook%3Aone' }) }))
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('../components/NotebookHeader', () => ({ NotebookHeader: () => <h1 id="notebook-title">Field notebook</h1> }))
vi.mock('../components/SourcesColumn', () => ({ SourcesColumn: () => <div>Sources column</div> }))
vi.mock('../components/NotesColumn', () => ({ NotesColumn: () => <div>Notes column</div> }))
vi.mock('../components/ChatColumn', async () => {
  const { useEffect } = await import('react')
  return {
    ChatColumn: () => {
      useEffect(() => { chatMounts.count += 1 }, [])
      return <div>Chat column</div>
    },
  }
})
vi.mock('@/components/research/ResearchRunWorkspace', () => ({ ResearchRunWorkspace: () => <div>Research workspace</div> }))
vi.mock('@/components/deeper-notebook', () => ({ ArtifactRail: () => <div>Artifact rail</div> }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebook: () => ({ data: { id: 'notebook:one', name: 'Field notebook' }, isLoading: false }) }))
vi.mock('@/lib/hooks/use-sources', () => ({ useNotebookSources: () => ({ sources: [], isLoading: false, refetch: vi.fn(), hasNextPage: false, isFetchingNextPage: false, fetchNextPage: vi.fn() }) }))
vi.mock('@/lib/hooks/use-notes', () => ({ useNotes: () => ({ data: [], isLoading: false }) }))
vi.mock('@/lib/stores/notebook-columns-store', () => ({ useNotebookColumnsStore: () => ({ sourcesCollapsed: false, notesCollapsed: false, studioCollapsed: false, setSources: vi.fn(), setNotes: vi.fn(), setStudio: vi.fn(), toggleStudio: vi.fn() }) }))
vi.mock('@/lib/hooks/use-media-query', () => ({ useIsDesktop: mockUseIsDesktop, useIsWideDesktop: mockUseIsWideDesktop }))
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
    mockUseIsWideDesktop.mockReturnValue(true)
  })

  // v0.8.130 — Phase 2a: the workspace is its own bounded page, named by the
  // notebook's title (the single h1), not a folio titled "Notebook workspace".
  it('is a main region named by the notebook title, without the folio eyebrow', () => {
    render(<NotebookPage />)

    const main = screen.getByRole('main', { name: 'Field notebook' })
    expect(main).toHaveAttribute('data-dn-notebook-workspace')
    expect(screen.queryByText('Organize')).not.toBeInTheDocument()
    expect(screen.queryByRole('main', { name: 'Notebook workspace' })).not.toBeInTheDocument()
  })

  it('lays the desktop columns out as Sources, Chat, Notes, Studio', () => {
    render(<NotebookPage />)

    const order = ['Sources column', 'Chat column', 'Notes column', 'Research workspace']
      .map((text) => screen.getByText(text))
    for (let i = 1; i < order.length; i++) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })

  it('moves Guided research and the Evidence Studio band into the Studio column', () => {
    render(<NotebookPage />)

    const studio = screen.getByRole('region', { name: 'notebooks.studio' })
    expect(studio).toContainElement(screen.getByText('Research workspace'))
    expect(studio).toContainElement(screen.getByText('Artifact rail'))
  })

  // v0.8.130 — four columns gave Notes and Studio ~120px each at 1024px and
  // clipped their controls. From 1024 to 1279px they share one side panel.
  it('puts Notes and Studio in one tabbed side panel on compact desktops', async () => {
    mockUseIsWideDesktop.mockReturnValue(false)
    const { fireEvent } = await import('@testing-library/react')
    render(<NotebookPage />)

    const side = screen.getByRole('tablist', { name: 'notebooks.notesAndStudio' })
    expect(side).toBeInTheDocument()
    expect(screen.getByText('Notes column')).toBeInTheDocument()
    expect(screen.queryByText('Research workspace')).not.toBeInTheDocument()

    fireEvent.mouseDown(screen.getByRole('tab', { name: 'notebooks.studio' }))
    expect(await screen.findByText('Research workspace')).toBeInTheDocument()
    expect(screen.queryByText('Notes column')).not.toBeInTheDocument()
  })

  it('offers Sources, Chat, Notes and Studio tabs on small screens', () => {
    mockUseIsDesktop.mockReturnValue(false)
    render(<NotebookPage />)

    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'navigation.sources', 'common.chat', 'common.notes', 'notebooks.studio',
    ])
  })

  // v0.8.130 — useIsDesktop reports false on the first render (SSR-safe), so a
  // desktop load used to mount the mobile chat for one tick before the desktop
  // one: a duplicate set of session, note and context requests, and which of
  // them fired depended on timing. The columns now render once the viewport is known.
  it('mounts the chat exactly once on a desktop load', async () => {
    const { useEffect, useState } = await import('react')
    mockUseIsDesktop.mockImplementation(() => {
      const [desktop, setDesktop] = useState(false)
      useEffect(() => setDesktop(true), [])
      return desktop
    })
    chatMounts.count = 0

    render(<NotebookPage />)

    expect(await screen.findByText('Chat column')).toBeInTheDocument()
    expect(chatMounts.count).toBe(1)
  })

  it('mounts one mobile chat column without mounting the CSS-hidden desktop pane', () => {
    mockUseIsDesktop.mockReturnValue(false)

    render(<NotebookPage />)

    expect(screen.getAllByText('Chat column')).toHaveLength(1)
  })
})
