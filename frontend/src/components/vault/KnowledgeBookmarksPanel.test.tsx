import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBookmark } from '@/lib/api/knowledge-navigation'
import { KnowledgeBookmarksPanel } from './KnowledgeBookmarksPanel'

const externalBookmark = (): KnowledgeBookmark => ({
  schemaVersion: 1,
  id: 'knowledge_bookmark:research',
  targetKind: 'document',
  target: { kind: 'document', documentId: 'knowledge_engine_document:research' },
  displayLabel: 'Research plan', authorityKind: 'external_read_only',
  spaceId: 'knowledge_engine_space:research', folderId: null, tags: ['plans'], position: 0,
  revision: 1, createdAt: '2026-07-31T00:00:00.000Z', updatedAt: '2026-07-31T00:00:00.000Z',
  targetState: 'available',
  targetDocument: {
    documentId: 'knowledge_engine_document:research', spaceId: 'knowledge_engine_space:research',
    authorityKind: 'external_read_only', sourceKind: 'markdown', title: 'Research plan',
    relativeLocator: 'Research/Plan.md', legacyNoteId: 'note:research', legacyContainerId: 'vault:research',
  },
})

describe('KnowledgeBookmarksPanel', () => {
  it('shows external target authority while keeping bookmark metadata editable', () => {
    render(<KnowledgeBookmarksPanel bookmarks={[externalBookmark()]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.getByText('External read-only')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Edit bookmark Research plan' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /edit source/i })).not.toBeInTheDocument()
  })

  it('limits a stale target to repair and deletion controls', () => {
    const stale = { ...externalBookmark(), targetState: 'stale' as const }
    render(<KnowledgeBookmarksPanel bookmarks={[stale]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Open Research plan' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit Target Research plan' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Edit bookmark Research plan' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete bookmark Research plan' })).toBeVisible()
  })
})
