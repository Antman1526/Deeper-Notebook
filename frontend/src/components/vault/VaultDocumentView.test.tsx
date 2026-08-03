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

const mixedNewlineMarkdown = '# ATX\r\nBody\r\rSetext\r------\r\n## Tail'

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
  it('emits the validated block identity on the readable block container', () => {
    renderDocument('reading', pageFixtureWith({
      blocks: [{ knowledge_block_id: 'knowledge_engine_block:plan', source_revision_id: 'knowledge_engine_revision:one', markdown: '# Plan' }],
    }))

    const block = document.querySelector('[data-knowledge-block-id="knowledge_engine_block:plan"]')
    expect(block).toHaveAttribute('data-source-revision-id', 'knowledge_engine_revision:one')
  })

  it('keeps duplicate readable text in distinct validated block containers', () => {
    renderDocument('reading', pageFixtureWith({
      blocks: [
        { knowledge_block_id: 'knowledge_engine_block:first', source_revision_id: 'knowledge_engine_revision:one', markdown: 'Repeated' },
        { knowledge_block_id: 'knowledge_engine_block:second', source_revision_id: 'knowledge_engine_revision:two', markdown: 'Repeated' },
      ],
    }))

    expect(document.querySelectorAll('[data-knowledge-block-id]').length).toBe(2)
    expect(document.querySelector('[data-knowledge-block-id="knowledge_engine_block:second"]'))
      .toHaveAttribute('data-source-revision-id', 'knowledge_engine_revision:two')
  })

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
    expect(ids[0]).toMatch(/^v-/)
    expect(ids[1]).toMatch(/^v-/)

    fireEvent.click(screen.getAllByRole('button', { name: 'Level 1 Plan' })[1])
    expect(firstScroll).not.toHaveBeenCalled()
    expect(secondScroll).toHaveBeenCalledWith({ block: 'start' })
  })

  it('builds ATX and Setext outline entries across mixed CR and CRLF input', () => {
    renderDocument('reading', pageFixtureWith({
      note: { content: mixedNewlineMarkdown },
    }))

    expect(screen.getByRole('button', { name: 'Level 1 ATX' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Level 2 Setext' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Level 2 Tail' }))
      .toBeInTheDocument()
  })

  it.each([
    ['source', 'Level 2 Setext', 'Setext'],
    ['live-preview', 'Level 2 Setext', 'Setext'],
    ['source', 'Level 2 Tail', '## Tail'],
    ['live-preview', 'Level 2 Tail', '## Tail'],
  ] as const)(
    'moves the %s editor to the exact mixed-newline offset for %s',
    (mode, outlineLabel, sourceNeedle) => {
      renderDocument(mode, pageFixtureWith({
        note: { content: mixedNewlineMarkdown },
      }))
      const editor = screen.getByRole('textbox')
      const view = EditorView.findFromDOM(editor)!

      fireEvent.click(screen.getByRole('button', { name: outlineLabel }))

      const rawOffset = mixedNewlineMarkdown.indexOf(sourceNeedle)
      const editorOffset = mixedNewlineMarkdown
        .slice(0, rawOffset)
        .replace(/\r\n?/g, '\n')
        .length
      expect(view.state.selection.main.head).toBe(editorOffset)
    },
  )

  it.each(['source', 'live-preview'] as const)('maps %s editor selection to its owned duplicate block range', (mode) => {
    const onFocusedBlockChange = vi.fn()
    const page = pageFixtureWith({
      note: { content: 'Repeated\nRepeated' },
      blocks: [
        { knowledge_block_id: 'knowledge_engine_block:first', source_revision_id: 'knowledge_engine_revision:one', markdown: 'Repeated' },
        { knowledge_block_id: 'knowledge_engine_block:second', source_revision_id: 'knowledge_engine_revision:two', markdown: 'Repeated' },
      ],
    })
    render(<VaultDocumentView viewId="pane-1:tab-1" mode={mode} page={page} onNavigate={vi.fn()} onFocusedBlockChange={onFocusedBlockChange} />)
    const view = EditorView.findFromDOM(screen.getByRole('textbox'))!

    act(() => view.dispatch({ selection: { anchor: 9, head: 10 } }))
    expect(onFocusedBlockChange).toHaveBeenLastCalledWith({ blockId: 'knowledge_engine_block:second', sourceRevisionId: 'knowledge_engine_revision:two' })
    act(() => view.dispatch({ selection: { anchor: 9 } }))
    expect(onFocusedBlockChange).toHaveBeenLastCalledWith(null)
  })

  it.each([
    ['pane:a', 'pane-a'],
    ['1:pane', 'pane:1'],
    ['pane/a', 'pane-a'],
    ['pane a', 'pane-a'],
    ['é', 'e\u0301'],
  ] as const)(
    'uses safe injective heading prefixes for %s and %s',
    (firstViewId, secondViewId) => {
      render(
        <>
          <VaultDocumentView
            viewId={firstViewId}
            mode="reading"
            page={pageFixture}
            onNavigate={vi.fn()}
          />
          <VaultDocumentView
            viewId={secondViewId}
            mode="reading"
            page={pageFixture}
            onNavigate={vi.fn()}
          />
        </>,
      )

      const headings = screen.getAllByRole('heading', { name: 'Plan' })
      const ids = headings.map((heading) => heading.id)
      expect(ids.every((id) => id.startsWith('v-'))).toBe(true)
      expect(new Set(ids).size).toBe(ids.length)

      const firstScroll = vi.fn()
      const secondScroll = vi.fn()
      headings[0].scrollIntoView = firstScroll
      headings[1].scrollIntoView = secondScroll
      expect(() => {
        fireEvent.click(screen.getAllByRole('button', { name: 'Level 1 Plan' })[1])
      }).not.toThrow()
      expect(firstScroll).not.toHaveBeenCalled()
      expect(secondScroll).toHaveBeenCalledWith({ block: 'start' })
    },
  )

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
