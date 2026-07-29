import { act, fireEvent, render, screen } from '@testing-library/react'
import { EditorView } from '@codemirror/view'
import { describe, expect, it, vi } from 'vitest'

import type { VaultPage } from '@/lib/api/vault'

import { VaultDocumentView } from './VaultDocumentView'

const pageFixture: VaultPage = {
  file: {
    id: 'file:plan',
    note_id: 'note:plan',
    vault_id: 'vault:research',
    relative_path: 'pages/plan.md',
    file_kind: 'note',
    format: 'markdown',
    content_hash: 'a'.repeat(64),
    parse_status: 'parsed',
    size_bytes: 28,
    modified_ns: 1,
    encoding: 'utf-8',
    newline: 'lf',
    deleted_state: 'present',
  },
  note: {
    id: 'note:plan',
    title: 'Plan',
    content: '# Plan\n\n## Evidence',
    markdown: '# Stale fallback',
    properties: {},
    tags: [],
  },
  blocks: [{ markdown: '# Stale block' }],
  tasks: [],
  outgoing_links: [],
  backlinks: [],
}

function pageFixtureWith(
  overrides: Omit<Partial<VaultPage>, 'note' | 'file'> & {
    note?: Partial<VaultPage['note']>
    file?: Partial<VaultPage['file']>
  },
): VaultPage {
  return {
    ...pageFixture,
    ...overrides,
    file: { ...pageFixture.file, ...overrides.file },
    note: { ...pageFixture.note, ...overrides.note },
  }
}

function renderDocument(
  mode: 'reading' | 'source' | 'live-preview',
  page: VaultPage = pageFixture,
  viewId = 'pane-1:tab-1',
) {
  return render(
    <VaultDocumentView
      viewId={viewId}
      mode={mode}
      page={page}
      onNavigate={vi.fn()}
      onPreview={vi.fn()}
    />,
  )
}

describe('VaultDocumentView', () => {
  it.each([
    ['reading', 'Plan reading view'],
    ['source', 'Plan source'],
    ['live-preview', 'Plan live preview'],
  ] as const)('renders %s mode', (mode, accessibleName) => {
    renderDocument(mode)
    if (mode === 'reading') {
      expect(screen.getByRole('region', { name: accessibleName })).toBeInTheDocument()
    } else {
      expect(screen.getByRole('textbox', { name: accessibleName })).toBeInTheDocument()
    }
    expect(screen.getByLabelText('Note details')).toBeInTheDocument()
  })

  it.each(['reading', 'source', 'live-preview'] as const)(
    'renders an explicit empty-note state in %s mode without an editor',
    (mode) => {
      renderDocument(mode, pageFixtureWith({ note: { content: '' } }))

      expect(screen.getByText('knowledge.emptyNote')).toBeInTheDocument()
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    },
  )

  it('preserves an explicitly empty canonical content field', () => {
    renderDocument('reading', pageFixtureWith({
      note: { content: '', markdown: '# Stale fallback' },
      blocks: [{ markdown: '# Stale block' }],
    }))

    expect(screen.getByText('knowledge.emptyNote')).toBeInTheDocument()
    expect(screen.queryByText('Stale fallback')).not.toBeInTheDocument()
    expect(screen.queryByText('Stale block')).not.toBeInTheDocument()
  })

  it('uses Markdown only when canonical content is nullish', () => {
    renderDocument('reading', pageFixtureWith({
      note: { content: undefined, markdown: '# Markdown fallback' },
      blocks: [{ markdown: '# Stale block' }],
    }))

    expect(screen.getByRole('heading', { name: 'Markdown fallback' }))
      .toBeInTheDocument()
    expect(screen.queryByText('Stale block')).not.toBeInTheDocument()
  })

  it('isolates duplicate Reading headings to the owning split-pane container', () => {
    render(
      <>
        <VaultDocumentView
          viewId="pane-1:tab-1"
          mode="reading"
          page={pageFixture}
          onNavigate={vi.fn()}
          onPreview={vi.fn()}
        />
        <VaultDocumentView
          viewId="pane-2:tab-2"
          mode="reading"
          page={pageFixture}
          onNavigate={vi.fn()}
          onPreview={vi.fn()}
        />
      </>,
    )

    const headings = screen.getAllByRole('heading', { name: 'Plan' })
    const firstScroll = vi.fn()
    const secondScroll = vi.fn()
    headings[0].scrollIntoView = firstScroll
    headings[1].scrollIntoView = secondScroll

    const ids = headings.map((heading) => heading.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids[0]).toMatch(/^pane-1-tab-1-/)
    expect(ids[1]).toMatch(/^pane-2-tab-2-/)

    fireEvent.click(screen.getAllByRole('button', { name: 'Level 1 Plan' })[1])
    expect(firstScroll).not.toHaveBeenCalled()
    expect(secondScroll).toHaveBeenCalledWith({ block: 'start' })
  })

  it.each(['source', 'live-preview'] as const)(
    'moves the %s editor to the exact outline source offset',
    (mode) => {
      renderDocument(mode)
      const editor = screen.getByRole('textbox')
      const view = EditorView.findFromDOM(editor)!

      act(() => {
        fireEvent.click(screen.getByRole('button', { name: 'Level 2 Evidence' }))
      })

      expect(view.state.selection.main.head)
        .toBe(pageFixture.note.content!.indexOf('## Evidence'))
    },
  )
})
