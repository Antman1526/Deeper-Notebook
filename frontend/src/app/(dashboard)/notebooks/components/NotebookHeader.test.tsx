import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { NotebookResponse } from '@/lib/types/api'

import { NotebookHeader } from './NotebookHeader'

// T0-12 — the header rendered "Created 9 months ago •Updated 9 months ago" (JSX
// trims the space before a line break, so the bullet touched "Updated"), and the
// description broke in the middle of a word on narrow screens ("wit / h").

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'common.created': 'Created {time}',
      'common.updated': 'Updated {time}',
      'notebooks.aboutNotebook': 'About this notebook',
      'notebooks.actions': 'Notebook actions',
    }[key] ?? key),
    language: 'en-US',
  }),
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useUpdateNotebook: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}))
vi.mock('./NotebookDeleteDialog', () => ({ NotebookDeleteDialog: () => null }))
vi.mock('./ExportNotebookDialog', () => ({ ExportNotebookDialog: () => null }))
vi.mock('@/components/notebooks/ExecutiveSynthesisDialog', () => ({ ExecutiveSynthesisDialog: () => null }))
vi.mock('@/components/notebooks/MindMapButton', () => ({ MindMapButton: () => <button type="button">Mind map</button> }))

const notebook: NotebookResponse = {
  id: 'notebook:abc',
  name: 'Deterministic Research Notebook',
  description: 'A browser-harness notebook with fixed evidence.',
  archived: false,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-02T00:00:00Z',
  source_count: 1,
  note_count: 0,
}

// v0.8.130 — Phase 2a: a 56px top bar. The title is the page's single h1; the
// description and dates live behind "About this notebook"; Archive, Export and
// Delete live in the "Notebook actions" menu.
const openAbout = () => fireEvent.click(screen.getByRole('button', { name: 'About this notebook' }))

describe('NotebookHeader', () => {
  it('makes the editable notebook title the page heading', () => {
    render(<NotebookHeader notebook={notebook} />)

    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveAttribute('id', 'notebook-title')
    expect(heading).toHaveTextContent(notebook.name)
    expect(heading).toContainElement(screen.getByRole('button', { name: notebook.name }))
  })

  it('separates the created and updated times with a spaced bullet', () => {
    render(<NotebookHeader notebook={notebook} />)
    openAbout()

    const meta = screen.getByText(/^Created .* • Updated /)
    expect(meta.textContent).toMatch(/ago • Updated .* ago$/)
  })

  it('wraps the description at word boundaries instead of inside words', () => {
    render(<NotebookHeader notebook={notebook} />)
    openAbout()

    const description = screen.getByRole('button', { name: notebook.description })
    expect(description.className).toContain('[overflow-wrap:anywhere]')
    expect(description.className).not.toContain('break-all')
  })

  it('keeps Archive, Export and Delete in the notebook actions menu', () => {
    render(<NotebookHeader notebook={notebook} />)
    expect(screen.queryByRole('menuitem', { name: /archive/i })).not.toBeInTheDocument()

    fireEvent.keyDown(screen.getByRole('button', { name: 'Notebook actions' }), { key: 'ArrowDown' })

    expect(screen.getByRole('menuitem', { name: 'notebooks.archive' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'notebooks.export.button' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'common.delete' })).toBeInTheDocument()
  })

  it('keeps Synthesis and Mind map one click away', () => {
    render(<NotebookHeader notebook={notebook} />)

    expect(screen.getByTestId('executive-synthesis-button')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mind map' })).toBeInTheDocument()
  })
})
