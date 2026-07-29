import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VaultMarkdown } from './VaultMarkdown'

const resolvedLinkFixture = {
  id: 'link:research',
  source_note_id: 'note:plan',
  target_note_id: 'note:research',
  target_note_title: 'Research',
  target_relative_path: 'pages/research.md',
  target_text: 'Research',
  link_kind: 'wikilink',
  resolved: true,
  source_start: 0,
  source_end: 12,
}

const unresolvedLinkFixture = {
  ...resolvedLinkFixture,
  id: 'link:missing',
  target_note_id: null,
  target_note_title: null,
  target_relative_path: null,
  target_text: 'pages/missing.md',
  resolved: false,
}

describe('VaultMarkdown', () => {
  it('renders markdown without executing raw HTML and navigates resolved wikilinks', () => {
    const onNavigate = vi.fn()
    render(<VaultMarkdown markdown={'# Plan\n\n[[Research]]\n\n<img src=x onerror=alert(1)>'} links={[{
      id: 'link:1',
      source_note_id: 'note:one',
      target_note_id: 'note:two',
      target_text: 'Research',
      link_kind: 'wikilink',
      resolved: true,
      source_start: 8,
      source_end: 20,
    }]} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))
    expect(onNavigate).toHaveBeenCalledWith('note:two')
    expect(document.querySelector('img')).toBeNull()
  })
})

describe('VaultMarkdown reading mode', () => {
  it('renders GFM footnotes math anchors and disabled tasks safely', () => {
    render(
      <VaultMarkdown
        noteId="note:plan"
        headingIdPrefix="pane-1-tab-1"
        markdown={[
          '# Plan',
          '# Plan',
          '',
          '- [ ] Review',
          '',
          'Evidence[^1] and $x^2$.',
          '',
          '[^1]: Source note',
        ].join('\n')}
        links={[]}
        onNavigate={vi.fn()}
        onPreview={vi.fn()}
        footnoteLabel="Footnotes"
      />,
    )

    const headings = screen.getAllByRole('heading', { name: 'Plan' })
    expect(headings[0]).toHaveAttribute('id', 'pane-1-tab-1-plan')
    expect(headings[1]).toHaveAttribute('id', 'pane-1-tab-1-plan-1')
    expect(screen.getByRole('checkbox', { name: /review/i })).toBeDisabled()
    expect(document.querySelector('.katex')).not.toBeNull()
    expect(screen.getByRole('doc-noteref')).toBeInTheDocument()
  })

  it('keeps external links inert and previews resolved internal links', () => {
    const onPreview = vi.fn()
    render(
      <VaultMarkdown
        noteId="note:plan"
        headingIdPrefix="pane-1-tab-1"
        markdown={'[[Research]] and [Web](https://example.com)'}
        links={[resolvedLinkFixture]}
        onNavigate={vi.fn()}
        onPreview={onPreview}
        footnoteLabel="Footnotes"
      />,
    )

    fireEvent.focus(screen.getByRole('button', { name: 'Research' }))
    expect(onPreview).toHaveBeenCalledWith(resolvedLinkFixture)
    expect(screen.queryByRole('link', { name: 'Web' })).not.toBeInTheDocument()
  })

  it('maps a resolved Markdown link by its UTF-8 source span', () => {
    const markdown = 'é [Research](pages/research.md)'
    const sourceStart = new TextEncoder().encode('é ').length
    const sourceEnd = new TextEncoder().encode(markdown).length
    const onPreview = vi.fn()
    render(
      <VaultMarkdown
        noteId="note:plan"
        headingIdPrefix="pane-1-tab-1"
        markdown={markdown}
        links={[{
          ...resolvedLinkFixture,
          link_kind: 'markdown',
          target_text: 'pages/research.md',
          source_start: sourceStart,
          source_end: sourceEnd,
        }]}
        onNavigate={vi.fn()}
        onPreview={onPreview}
        footnoteLabel="Footnotes"
      />,
    )

    fireEvent.focus(screen.getByRole('button', { name: 'Research' }))
    expect(onPreview).toHaveBeenCalled()
  })

  it('leaves an unresolved Markdown link inert', () => {
    render(
      <VaultMarkdown
        noteId="note:plan"
        headingIdPrefix="pane-1-tab-1"
        markdown={'[Missing](pages/missing.md)'}
        links={[{
          ...unresolvedLinkFixture,
          link_kind: 'markdown',
          source_start: 0,
          source_end: 27,
        }]}
        onNavigate={vi.fn()}
        onPreview={vi.fn()}
        footnoteLabel="Footnotes"
      />,
    )
    expect(screen.queryByRole('button', { name: 'Missing' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Missing' })).not.toBeInTheDocument()
  })

  it('keeps duplicate wiki-link labels bound to their exact source spans', () => {
    const first = { ...resolvedLinkFixture, id: 'link:first', target_note_id: 'note:first', source_start: 0, source_end: 17 }
    const second = { ...resolvedLinkFixture, id: 'link:second', target_note_id: 'note:second', source_start: 23, source_end: 40 }
    const onNavigate = vi.fn()
    render(
      <VaultMarkdown
        noteId="note:plan"
        headingIdPrefix="pane-1-tab-1"
        markdown="[[Research|Same]] then [[Research|Same]]"
        links={[first, second]}
        onNavigate={onNavigate}
        onPreview={vi.fn()}
        footnoteLabel="Footnotes"
      />,
    )

    const links = screen.getAllByRole('button', { name: 'Same' })
    fireEvent.click(links[0])
    fireEvent.click(links[1])
    expect(onNavigate).toHaveBeenNthCalledWith(1, 'note:first')
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'note:second')
  })
})
