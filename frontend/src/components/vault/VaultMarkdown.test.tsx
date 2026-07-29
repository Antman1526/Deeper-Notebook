import { fireEvent, render, screen, within } from '@testing-library/react'
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
      target_note_title: 'Research',
      target_relative_path: 'research.md',
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

  it('namespaces generated footnotes to each rendered view', () => {
    const markdown = 'Evidence[^1].\n\n[^1]: Local source'
    render(
      <>
        <section data-testid="first-view">
          <VaultMarkdown noteId="note:same" headingIdPrefix="Pane One / Tab" markdown={markdown} links={[]} onNavigate={vi.fn()} footnoteLabel="Footnotes" />
        </section>
        <section data-testid="second-view">
          <VaultMarkdown noteId="note:same" headingIdPrefix="Pane Two / Tab" markdown={markdown} links={[]} onNavigate={vi.fn()} footnoteLabel="Footnotes" />
        </section>
      </>,
    )

    const firstView = screen.getByTestId('first-view')
    const secondView = screen.getByTestId('second-view')
    const firstReference = within(firstView).getByRole('doc-noteref')
    const secondReference = within(secondView).getByRole('doc-noteref')
    const firstHref = firstReference.getAttribute('href')!
    const secondHref = secondReference.getAttribute('href')!
    expect(firstHref).not.toBe(secondHref)
    expect(firstHref).not.toMatch(/[\s/]/)
    expect(firstView.contains(document.getElementById(firstHref.slice(1)))).toBe(true)
    expect(secondView.contains(document.getElementById(secondHref.slice(1)))).toBe(true)

    const firstDescription = firstReference.getAttribute('aria-describedby')!
    const secondDescription = secondReference.getAttribute('aria-describedby')!
    expect(firstDescription).not.toBe(secondDescription)
    expect(firstView.contains(document.getElementById(firstDescription))).toBe(true)
    expect(secondView.contains(document.getElementById(secondDescription))).toBe(true)

    const ids = Array.from(document.querySelectorAll('[id]'), (element) => element.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('renders resolved wiki and Markdown attachments as inert metadata', () => {
    const wikiMarkdown = '[[photo.png]]'
    const markdownAttachment = '[Photo](assets/photo.png?download=1#preview)'
    const svgAttachment = '[Vector](assets/vector.svg?download=1#preview)'
    render(
      <>
        <VaultMarkdown
          markdown={wikiMarkdown}
          links={[{ ...resolvedLinkFixture, target_text: 'photo.png', source_start: 0, source_end: new TextEncoder().encode(wikiMarkdown).length }]}
          onNavigate={vi.fn()}
        />
        <VaultMarkdown
          markdown={markdownAttachment}
          links={[{ ...resolvedLinkFixture, link_kind: 'markdown', target_text: 'assets/photo.png?download=1#preview', source_start: 0, source_end: new TextEncoder().encode(markdownAttachment).length }]}
          onNavigate={vi.fn()}
        />
        <VaultMarkdown
          markdown={svgAttachment}
          links={[{ ...resolvedLinkFixture, link_kind: 'markdown', target_text: 'assets/vector.svg?download=1#preview', source_start: 0, source_end: new TextEncoder().encode(svgAttachment).length }]}
          onNavigate={vi.fn()}
        />
      </>,
    )

    expect(screen.queryByRole('button', { name: /photo|vector/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /photo|vector/i })).not.toBeInTheDocument()
    for (const label of screen.getAllByText(/photo|vector/i)) {
      expect(label).toHaveClass('text-muted-foreground')
    }
  })

  it.each([
    ['PNG alt text', '![Photo](assets/photo.png)', 'Photo'],
    ['SVG filename fallback', '![](assets/diagram.svg?raw=1#preview)', 'diagram.svg'],
  ])('renders %s as inert text without loading image bytes', (_label, markdown, expectedLabel) => {
    render(<VaultMarkdown markdown={markdown} links={[]} onNavigate={vi.fn()} />)

    expect(document.querySelector('img')).toBeNull()
    expect(screen.queryByRole('link', { name: expectedLabel })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: expectedLabel })).not.toBeInTheDocument()
    expect(screen.getByText(expectedLabel)).toHaveClass('text-muted-foreground')
  })

  it.each([
    ['first record first', false],
    ['second record first', true],
  ])('keeps a conflicting source span inert with %s', (_label, reverse) => {
    const markdown = '[[Research]]'
    const links = [
      { ...resolvedLinkFixture, id: 'first', target_note_id: 'note:first' },
      { ...resolvedLinkFixture, id: 'second', target_note_id: 'note:second' },
    ]
    render(
      <VaultMarkdown
        markdown={markdown}
        links={reverse ? links.reverse() : links}
        onNavigate={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Research' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Research' })).not.toBeInTheDocument()
  })

  it('indexes outgoing spans once instead of scanning every link for every anchor', () => {
    const markdown = Array.from({ length: 80 }, (_, index) => `[[Note-${index}]]`).join(' ')
    const records = Array.from({ length: 500 }, (_, index) => ({
      ...resolvedLinkFixture,
      id: `irrelevant-${index}`,
      source_start: markdown.length + index,
      source_end: markdown.length + index + 1,
    }))
    let indexedReads = 0
    const links = new Proxy(records, {
      get(target, property, receiver) {
        if (typeof property === 'string' && /^\d+$/.test(property)) indexedReads += 1
        return Reflect.get(target, property, receiver)
      },
    })

    render(<VaultMarkdown markdown={markdown} links={links} onNavigate={vi.fn()} />)

    expect(indexedReads).toBeLessThan(records.length * 2)
  })
})
