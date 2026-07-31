import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearKnowledgeCommandContext,
  registerKnowledgeCommandContext,
  resetKnowledgeCommandContextStore,
  useKnowledgeCommandContextStore,
} from './knowledge-command-context-store'

beforeEach(() => {
  useKnowledgeCommandContextStore.setState({ generation: 0, context: null })
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

  it('does not reuse a generation token after reset', () => {
    const first = registerKnowledgeCommandContext({ selectedVaultId: 'vault:first' })
    resetKnowledgeCommandContextStore()
    const second = registerKnowledgeCommandContext({ selectedVaultId: 'vault:second' })

    expect(second).toBe(2)
    clearKnowledgeCommandContext(first)
    expect(useKnowledgeCommandContextStore.getState().context?.selectedVaultId)
      .toBe('vault:second')
  })

  it('retains every navigation-productivity callback for the active page generation', () => {
    const callbacks = {
      bookmarkCurrentTarget: async () => undefined,
      openBookmarks: () => undefined,
      randomNote: async () => undefined,
      openWorkspaces: () => undefined,
      saveWorkspaceAs: () => undefined,
      replaceWorkspace: () => undefined,
      toggleMetrics: () => undefined,
    }

    registerKnowledgeCommandContext({ selectedVaultId: 'vault:one', ...callbacks })

    expect(useKnowledgeCommandContextStore.getState().context).toMatchObject(callbacks)
  })
})
