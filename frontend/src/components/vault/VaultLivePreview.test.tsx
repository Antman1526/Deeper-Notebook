import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VaultLivePreview } from './VaultLivePreview'

const resolvedLinkFixture = {
  id: 'link:research',
  source_note_id: 'note:plan',
  target_note_id: 'note:research',
  target_note_title: 'Research',
  target_relative_path: 'pages/research.md',
  target_text: 'Research',
  link_kind: 'wikilink',
  resolved: true,
  source_start: 8,
  source_end: 20,
}

describe('VaultLivePreview', () => {
  it('renders live preview as a locked editor with navigable wiki links', () => {
    const onNavigate = vi.fn()
    render(
      <VaultLivePreview
        title="Plan"
        markdown={'# Plan\n\n[[Research]]'}
        links={[resolvedLinkFixture]}
        onNavigate={onNavigate}
      />,
    )

    expect(screen.getByRole('textbox', { name: 'Plan live preview' }))
      .toHaveAttribute('aria-readonly', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))
    expect(onNavigate).toHaveBeenCalledWith('note:research')
  })

  it('navigates a resolved Markdown link by its UTF-8 source span', () => {
    const markdown = 'é [Research](pages/research.md)'
    const onNavigate = vi.fn()
    render(
      <VaultLivePreview
        title="Plan"
        markdown={markdown}
        links={[{
          ...resolvedLinkFixture,
          link_kind: 'markdown',
          source_start: new TextEncoder().encode('é ').length,
          source_end: new TextEncoder().encode(markdown).length,
        }]}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Research' }))
    expect(onNavigate).toHaveBeenCalledWith('note:research')
  })

  it('does not navigate unresolved, external, or attachment links', () => {
    const onNavigate = vi.fn()
    const external = '[External](https://example.test)'
    const attachment = '[Attachment](chart.pdf)'
    const unresolved = '[[Unresolved]]'
    const markdown = `prefix ${external} ${attachment} ${unresolved}`
    const byteLength = (value: string) => new TextEncoder().encode(value).length
    const externalStart = byteLength('prefix ')
    const attachmentStart = externalStart + byteLength(`${external} `)
    const unresolvedStart = attachmentStart + byteLength(`${attachment} `)
    render(
      <VaultLivePreview
        title="Plan"
        markdown={markdown}
        links={[
          { ...resolvedLinkFixture, source_start: externalStart, source_end: externalStart + byteLength(external) },
          { ...resolvedLinkFixture, source_start: attachmentStart, source_end: attachmentStart + byteLength(attachment) },
          { ...resolvedLinkFixture, resolved: false, target_note_id: null, source_start: unresolvedStart, source_end: unresolvedStart + byteLength(unresolved) },
        ]}
        onNavigate={onNavigate}
      />,
    )

    expect(screen.queryByRole('button')).toBeNull()
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('only turns one canonical record for an exact source span into a navigation button', () => {
    const onNavigate = vi.fn()
    render(
      <VaultLivePreview
        title="Plan"
        markdown={'[[Research|Same]] then [[Research|Same]]'}
        links={[
          { ...resolvedLinkFixture, source_start: 0, source_end: 17 },
          { ...resolvedLinkFixture, id: 'duplicate', source_start: 0, source_end: 17 },
          { ...resolvedLinkFixture, id: 'second', target_note_id: 'note:second', source_start: 23, source_end: 40 },
        ]}
        onNavigate={onNavigate}
      />,
    )

    const buttons = screen.getAllByRole('button', { name: 'Same' })
    expect(buttons).toHaveLength(1)
    fireEvent.click(buttons[0])
    expect(onNavigate).toHaveBeenCalledWith('note:second')
  })
})
