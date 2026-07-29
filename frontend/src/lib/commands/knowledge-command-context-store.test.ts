import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearKnowledgeCommandContext,
  registerKnowledgeCommandContext,
  resetKnowledgeCommandContextStore,
  useKnowledgeCommandContextStore,
} from './knowledge-command-context-store'

beforeEach(() => {
  resetKnowledgeCommandContextStore()
})

describe('knowledge command context registration', () => {
  it('does not let stale cleanup clear a newer registration', () => {
    const first = registerKnowledgeCommandContext({ selectedVaultId: 'vault:first' })
    const second = registerKnowledgeCommandContext({ selectedVaultId: 'vault:second' })
    clearKnowledgeCommandContext(first)
    expect(useKnowledgeCommandContextStore.getState().context?.selectedVaultId)
      .toBe('vault:second')
    clearKnowledgeCommandContext(second)
    expect(useKnowledgeCommandContextStore.getState().context).toBeNull()
  })

  it('increments page generations from a reset state', () => {
    expect(registerKnowledgeCommandContext({ selectedVaultId: null })).toBe(1)
    expect(registerKnowledgeCommandContext({ selectedVaultId: 'vault:two' })).toBe(2)
  })
})
