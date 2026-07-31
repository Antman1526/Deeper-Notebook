import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { KnowledgeUtilityRail } from './KnowledgeUtilityRail'

describe('KnowledgeUtilityRail', () => {
  it('switches to bookmarks without replacing the active document', () => {
    const onNavigationChange = vi.fn()
    const activeDocumentId = 'knowledge_engine_document:research'
    render(
      <KnowledgeUtilityRail
        mode="sources"
        sidebarVisible
        canBookmarkCurrent={Boolean(activeDocumentId)}
        onNavigationChange={onNavigationChange}
        onToday={vi.fn()}
        onRandomNote={vi.fn()}
        onBookmarkCurrent={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Bookmarks' }))

    expect(screen.getByRole('navigation', { name: 'Bookmarks' })).toBeVisible()
    expect(onNavigationChange).toHaveBeenCalledWith({ utilityMode: 'bookmarks' })
    expect(activeDocumentId).toBe('knowledge_engine_document:research')
  })

  it('explains why the current target cannot be bookmarked without a unified ID', () => {
    render(
      <KnowledgeUtilityRail
        mode="sources"
        sidebarVisible
        canBookmarkCurrent={false}
        onNavigationChange={vi.fn()}
        onToday={vi.fn()}
        onRandomNote={vi.fn()}
        onBookmarkCurrent={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Bookmark Current Target' })).toBeDisabled()
    expect(screen.getByText('The active page has no unified document ID.')).toBeVisible()
  })
})
