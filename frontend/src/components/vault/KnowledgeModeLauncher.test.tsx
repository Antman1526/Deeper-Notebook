import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeTab } from '@/lib/api/knowledge-workspace'
import { KnowledgeModeLauncher } from './KnowledgeModeLauncher'

const readTab: KnowledgeTab = {
  id: 'tab-read', vaultId: 'vault:one', noteId: 'note:one', title: 'Research plan',
  relativePath: 'Projects/Research.md', viewMode: 'reading', sourceAuthority: 'external-vault',
  knowledgeDocumentId: 'doc:one', graphViewport: { x: 0, y: 0, zoom: 1 },
  mode: 'read', target: { kind: 'document', container_id: 'vault:one', note_id: 'note:one', title: 'Research plan', relative_locator: 'Projects/Research.md', authority: 'external-vault', knowledge_document_id: 'doc:one', render_mode: 'reading' },
}

describe('KnowledgeModeLauncher', () => {
  it('exposes all six modes through a roving-tabindex toolbar and Alt shortcuts', () => {
    const onActivateTab = vi.fn()
    const onOpenMode = vi.fn()
    render(
      <KnowledgeModeLauncher
        activePaneId="pane-1"
        tabs={[readTab]}
        onActivateTab={onActivateTab}
        onOpenMode={onOpenMode}
      />,
    )

    const toolbar = screen.getByRole('toolbar', { name: 'Research modes' })
    const modes = ['Read', 'Write', 'Ask', 'Search', 'Graph', 'Podcast']
    for (const mode of modes) {
      expect(screen.getByRole('button', { name: new RegExp(`${mode}.*Alt\\+`) })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: /Read.*Alt\+1/ })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('button', { name: /Write.*Alt\+2/ })).toHaveAttribute('tabindex', '-1')

    fireEvent.keyDown(toolbar, { key: '4', altKey: true })
    expect(onOpenMode).toHaveBeenCalledWith('search', 'pane-1')
    expect(onActivateTab).not.toHaveBeenCalled()

    const read = screen.getByRole('button', { name: /Read.*Alt\+1/ })
    const write = screen.getByRole('button', { name: /Write.*Alt\+2/ })
    read.focus()
    fireEvent.keyDown(toolbar, { key: 'ArrowRight' })
    expect(write).toHaveFocus()
    expect(write).toHaveAttribute('tabindex', '0')
  })

  it('activates a compatible tab and never replaces an unsaved Overlay draft', () => {
    const onActivateTab = vi.fn()
    const onOpenMode = vi.fn()
    const overlayDraft: KnowledgeTab = {
      ...readTab,
      id: 'tab-write',
      title: 'Draft',
      sourceAuthority: 'overlay',
      mode: 'write',
      target: {
        kind: 'document', container_id: 'vault:one', note_id: 'note:one', title: 'Draft',
        relative_locator: 'Projects/Draft.md', authority: 'overlay',
        knowledge_document_id: 'doc:one', render_mode: 'source',
      },
    }
    render(
      <KnowledgeModeLauncher
        activePaneId="pane-1"
        tabs={[readTab, overlayDraft]}
        activeTabId="tab-write"
        hasUnsavedOverlayDraft
        onActivateTab={onActivateTab}
        onOpenMode={onOpenMode}
      />,
    )

    fireEvent.keyDown(screen.getByRole('toolbar', { name: 'Research modes' }), {
      key: '1', altKey: true,
    })

    expect(onActivateTab).toHaveBeenCalledWith('pane-1', 'tab-read')
    expect(onOpenMode).not.toHaveBeenCalled()
    expect(screen.getByText('Unsaved Overlay draft remains open')).toBeInTheDocument()
  })
})
