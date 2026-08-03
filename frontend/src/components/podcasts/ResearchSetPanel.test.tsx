import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { PodcastSelectionPreview } from '@/lib/types/podcasts'
import { ResearchSetPanel } from './ResearchSetPanel'

const preview = (overrides: Partial<PodcastSelectionPreview> = {}): PodcastSelectionPreview => ({
  selectionFingerprint: 'a'.repeat(64),
  entries: [
    {
      stableId: 'knowledge_engine_document:one', title: 'Included note',
      authorityKind: 'app_owned', relativeLocator: null, revisionId: 'knowledge_engine_revision:r1',
      fingerprint: 'b'.repeat(64), state: 'included', reason: 'Included in the current worker', estimatedCharacters: 120,
    },
    {
      stableId: 'knowledge_engine_document:changed', title: 'Changed note',
      authorityKind: 'external_read_only', relativeLocator: 'notes/changed.md', revisionId: null,
      fingerprint: null, state: 'changed', reason: 'Revision changed after preview', estimatedCharacters: 0,
    },
    {
      stableId: 'knowledge_engine_document:duplicate', title: 'Duplicate note',
      authorityKind: 'app_owned', relativeLocator: null, revisionId: null, fingerprint: null,
      state: 'duplicate', reason: 'Exact reference already included', estimatedCharacters: 0,
    },
    {
      stableId: 'knowledge_engine_document:oversize', title: 'Oversize note',
      authorityKind: 'app_owned', relativeLocator: null, revisionId: null, fingerprint: null,
      state: 'oversize', reason: 'Requires batch engine', estimatedCharacters: 999,
    },
  ],
  includedCharacters: 120,
  requiresBatchEngine: true,
  currentWorkerEligible: false,
  blockedReasons: ['podcast_batch_engine_required'],
  ...overrides,
})

describe('ResearchSetPanel', () => {
  it('renders included, problem, duplicate, and oversize states without absolute paths', () => {
    render(<ResearchSetPanel selections={[]} preview={preview()} />)

    expect(screen.getByRole('region', { name: 'Research Set' })).toBeVisible()
    expect(screen.getByText('Included note')).toBeVisible()
    expect(screen.getByText('Changed note')).toBeVisible()
    expect(screen.getByText('Duplicate note')).toBeVisible()
    expect(screen.getByText('Oversize note')).toBeVisible()
    expect(screen.getByText('Selection requires a batch engine; the current worker will not truncate it.')).toBeVisible()
    expect(screen.queryByText(/\/Users\//)).not.toBeInTheDocument()
  })

  it('shows an explicit empty state and worker boundary', () => {
    render(<ResearchSetPanel selections={[]} preview={preview({ entries: [], includedCharacters: 0, requiresBatchEngine: false, currentWorkerEligible: false, blockedReasons: ['empty_selection'] })} />)

    expect(screen.getByText('No readable references selected')).toBeVisible()
    expect(screen.getByText(/current worker/i)).toBeVisible()
  })

  it('redacts absolute title and reason text before presentation', () => {
    render(<ResearchSetPanel selections={[]} preview={preview({ entries: [{
      stableId: 'knowledge_engine_document:private', title: '/Users/Antman/private.md', authorityKind: 'external_read_only',
      relativeLocator: '/Users/Antman/private.md', revisionId: null, fingerprint: null, state: 'unavailable',
      reason: 'cannot read /Users/Antman/private.md', estimatedCharacters: 0,
    }], blockedReasons: ['failed at /Users/Antman/private.md'] })} />)

    expect(screen.queryByText(/\/Users\/Antman/)).not.toBeInTheDocument()
    expect(screen.getByText('private.md')).toBeVisible()
  })

  it('redacts embedded POSIX, Windows, and file URLs in external preview text and attributes', () => {
    render(<ResearchSetPanel selections={[]} preview={preview({ entries: [{
      stableId: 'knowledge_engine_document:private',
      title: 'Imported from /Users/Antman/Secret/note.md',
      authorityKind: 'external_read_only', relativeLocator: 'C:\\Users\\Antman\\Secret\\note.md',
      revisionId: null, fingerprint: null, state: 'unavailable',
      reason: 'file:///Users/Antman/Secret/note.md and C:\\Users\\Antman\\Secret\\note.md', estimatedCharacters: 0,
    }], blockedReasons: ['failed at file:///Users/Antman/Secret/note.md'] })} />)

    expect(screen.queryByText(/\/Users\/Antman|C:\\Users\\Antman|file:/)).not.toBeInTheDocument()
    expect(screen.getByText('Imported from [path redacted]')).toBeVisible()
    expect(screen.getByText('[path redacted] and [path redacted]')).toBeVisible()
    expect(screen.getByText('Imported from [path redacted]')).toHaveAttribute('title', 'Imported from [path redacted]')
  })
})
