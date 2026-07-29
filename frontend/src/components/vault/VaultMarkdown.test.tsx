import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VaultMarkdown } from './VaultMarkdown'

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
