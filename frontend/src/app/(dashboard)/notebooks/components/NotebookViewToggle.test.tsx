import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useNotebookViewStore } from '@/lib/stores/notebook-view-store'

import { NotebookViewToggle } from './NotebookViewToggle'

// v0.8.130 — the notebooks page had a stored tile/list preference and a list view, but no
// control to change it, so the list view could not be reached. The toggle exposes it.

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('NotebookViewToggle', () => {
  beforeEach(() => {
    useNotebookViewStore.setState({ viewMode: 'tile' })
  })

  it('offers the two layouts as a labelled group of buttons', () => {
    render(<NotebookViewToggle />)

    const group = screen.getByRole('group', { name: 'notebooks.viewToggle' })
    expect(group).toContainElement(screen.getByRole('button', { name: 'notebooks.viewGrid' }))
    expect(group).toContainElement(screen.getByRole('button', { name: 'notebooks.viewList' }))
  })

  it('marks the current layout as pressed', () => {
    render(<NotebookViewToggle />)

    expect(screen.getByRole('button', { name: 'notebooks.viewGrid' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'notebooks.viewList' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('switches the stored layout, and back, when a button is pressed', () => {
    render(<NotebookViewToggle />)

    fireEvent.click(screen.getByRole('button', { name: 'notebooks.viewList' }))
    expect(useNotebookViewStore.getState().viewMode).toBe('list')
    expect(screen.getByRole('button', { name: 'notebooks.viewList' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'notebooks.viewGrid' })).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(screen.getByRole('button', { name: 'notebooks.viewGrid' }))
    expect(useNotebookViewStore.getState().viewMode).toBe('tile')
  })
})
