import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NotesColumn } from './NotesColumn'
import type { NoteResponse } from '@/lib/types/api'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

// v0.8.130 — resolve the real en-US strings so the accessible names asserted here are the
// ones a user (and the e2e specs) actually see.
vi.mock('@/lib/hooks/use-translation', async () => {
  const { enUS } = await import('@/lib/locales/en-US')
  const resolve = (key: string, options?: Record<string, unknown>): string => {
    let node: unknown = enUS
    for (const part of key.split('.')) {
      if (typeof node !== 'object' || node === null || !(part in (node as Record<string, unknown>))) return key
      node = (node as Record<string, unknown>)[part]
    }
    if (typeof node !== 'string') return key
    return options
      ? node.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, name: string) => (name in options ? String(options[name]) : match))
      : node
  }
  return { useTranslation: () => ({ t: resolve, i18n: { language: 'en-US' }, language: 'en-US', setLanguage: async () => 'en-US' }) }
})

const { mockNoteEditorDialog } = vi.hoisted(() => ({ mockNoteEditorDialog: vi.fn() }))

vi.mock('./NoteEditorDialog', () => ({
  NoteEditorDialog: (props: { open: boolean }) => {
    mockNoteEditorDialog(props)
    return null
  },
}))
vi.mock('./ExportNoteDialog', () => ({ ExportNoteDialog: () => null }))
vi.mock('@/components/common/ConfirmDialog', () => ({ ConfirmDialog: () => null }))
vi.mock('@/lib/hooks/use-notes', () => ({
  useDeleteNote: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/components/notebooks/CollapsibleColumn', () => ({
  CollapsibleColumn: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  createCollapseButton: () => null,
}))
vi.mock('@/lib/stores/notebook-columns-store', () => ({
  useNotebookColumnsStore: () => ({ notesCollapsed: false, toggleNotes: vi.fn() }),
}))

function note(overrides: Partial<NoteResponse> = {}): NoteResponse {
  return {
    id: 'note:1',
    title: 'Margin thoughts',
    content: 'Readable note content.',
    note_type: 'human',
    created: '2026-08-03T00:00:00Z',
    updated: '2026-08-03T00:00:00Z',
    ...overrides,
  } as NoteResponse
}

function openNoteActions() {
  fireEvent.keyDown(screen.getByRole('button', { name: 'Note actions' }), {
    key: 'ArrowDown',
    code: 'ArrowDown',
  })
}

describe('NotesColumn note cards', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    usePodcastStudioStore.getState().dismiss()
  })

  // v0.8.130 — the per-card "Turn into podcast" row repeated ~36px of chrome on every note;
  // it now lives in the card's overflow menu, as it does on source rows.
  it('offers Turn into podcast from the note actions menu instead of an inline row', () => {
    render(<NotesColumn notes={[note()]} isLoading={false} notebookId="notebook:one" />)

    expect(screen.queryByRole('button', { name: 'Turn into podcast' })).not.toBeInTheDocument()

    openNoteActions()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Turn into podcast' }))

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: true,
      destination: 'quick',
      selections: [{ kind: 'app_note', noteId: 'note:1' }],
    })
    // Choosing the action does not also open the note editor underneath.
    expect(mockNoteEditorDialog).toHaveBeenLastCalledWith(expect.objectContaining({ open: false }))
  })

  it('keeps the podcast menu item disabled, with its reason, when the note has no readable content', () => {
    render(<NotesColumn notes={[note({ content: '   ' })]} isLoading={false} notebookId="notebook:one" />)

    openNoteActions()

    expect(
      screen.getByRole('menuitem', { name: 'Turn into podcast — No readable note content is available.' })
    ).toHaveAttribute('data-disabled')
    expect(usePodcastStudioStore.getState().isOpen).toBe(false)
  })

  // v0.8.130 — the list sits on ruled paper; an opaque card hid the ruling. A translucent
  // paper fill (no blur) and a left index-tab accent whose width never changes on hover.
  it('gives note cards a translucent paper fill and a stable-width index-tab accent', () => {
    const { container } = render(<NotesColumn notes={[note()]} isLoading={false} notebookId="notebook:one" />)

    const card = container.querySelector('[data-dn-note-card]')
    expect(card).not.toBeNull()
    expect(card).toHaveClass('bg-card/90', 'border', 'border-l-2', 'border-l-primary/35', 'hover:border-l-primary', 'transition-colors')
    expect(card).not.toHaveClass('bg-card')
    expect(card?.className).not.toMatch(/backdrop-|hover:border-l-(?!primary\b)|hover:border-\d/)
  })
})
