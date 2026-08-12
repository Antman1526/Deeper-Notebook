import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { NotebookList } from './NotebookList'

vi.mock('@/lib/stores/notebook-view-store', () => ({
  useNotebookViewStore: (selector: (state: { viewMode: 'grid' }) => unknown) => selector({ viewMode: 'grid' }),
}))
vi.mock('./NotebookCard', () => ({
  NotebookCard: ({ notebook }: { notebook: { name: string } }) => <div data-testid="notebook-card">{notebook.name}</div>,
}))
vi.mock('./NotebookRow', () => ({ NotebookRow: ({ notebook }: { notebook: { name: string } }) => <div>{notebook.name}</div> }))
vi.mock('@/components/common/EmptyState', () => ({ EmptyState: () => <div>Empty notebooks</div> }))
vi.mock('@/lib/hooks/use-translation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

describe('NotebookList', () => {
  it('keeps populated cards single-column until the Folio content has room', () => {
    render(
      <NotebookList
        notebooks={[{ id: 'notebook-1', name: 'Research', description: '', archived: false, created: '', updated: '', source_count: 0, note_count: 0 }]}
        isLoading={false}
        title="Active notebooks"
      />,
    )

    const grid = screen.getByTestId('notebook-card').parentElement
    expect(grid).toHaveClass('grid-cols-1', 'xl:grid-cols-2', '2xl:grid-cols-3')
    expect(grid).not.toHaveClass('md:grid-cols-2', 'lg:grid-cols-3')
  })
})
