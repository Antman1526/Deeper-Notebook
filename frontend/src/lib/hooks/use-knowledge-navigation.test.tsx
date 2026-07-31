import { describe, expect, it } from 'vitest'

import { knowledgeNavigationKeys } from './use-knowledge-navigation'

describe('knowledge navigation hooks', () => {
  it('uses stable keys rooted at knowledge-navigation', () => {
    expect(knowledgeNavigationKeys.bookmarks({ tags: ['Evidence'] })).toEqual([
      'knowledge-navigation', 'bookmarks', { tags: ['Evidence'] },
    ])
  })
})
