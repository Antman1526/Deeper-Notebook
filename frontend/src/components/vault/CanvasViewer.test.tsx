import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { VaultCanvasDocument, VaultFile } from '@/lib/api/vault'

import { CanvasViewer } from './CanvasViewer'

const markdownFile: VaultFile = {
  id: 'vault_file:plan',
  note_id: 'note:plan',
  vault_id: 'vault_mount:one',
  relative_path: 'notes/Plan.md',
  file_kind: 'markdown',
  format: 'obsidian',
  content_hash: 'a'.repeat(64),
  parse_status: 'parsed',
  size_bytes: 128,
  modified_ns: 1,
  encoding: 'utf-8',
  newline: 'lf',
  deleted_state: 'present',
}

const canvas: VaultCanvasDocument = {
  file: {
    ...markdownFile,
    id: 'vault_file:canvas',
    note_id: 'note:canvas',
    relative_path: 'maps/Plan.canvas',
    file_kind: 'metadata',
  },
  source_hash: 'b'.repeat(64),
  nodes: [
    {
      id: 'idea', type: 'text', x: 0, y: 0, width: 100, height: 80,
      text: 'Idea', file_path: null, label: null,
    },
    {
      id: 'plan', type: 'file', x: 140, y: 0, width: 100, height: 80,
      text: null, file_path: 'notes/Plan.md', label: 'Plan',
    },
  ],
  edges: [{ id: 'edge', from_node: 'idea', to_node: 'plan', label: 'supports' }],
}

describe('CanvasViewer', () => {
  it('opens only a same-vault Markdown file node', () => {
    const onNavigate = vi.fn()

    render(
      <CanvasViewer
        canvas={canvas}
        vaultId="vault_mount:one"
        paneId="pane-1"
        files={[markdownFile]}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Plan' }))

    expect(onNavigate).toHaveBeenCalledWith(
      'vault_mount:one',
      'note:plan',
      'notes/Plan.md',
      'Plan',
      'pane-1',
      'Plan',
      'external-vault',
    )
    expect(screen.getByLabelText('Canvas viewer')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save|edit|delete/i })).not.toBeInTheDocument()
  })

  it('shows an alert with a retry action for an unavailable Canvas', () => {
    const onRetry = vi.fn()

    render(<CanvasViewer error={new Error('canvas_invalid')} onRetry={onRetry} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry Canvas' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
