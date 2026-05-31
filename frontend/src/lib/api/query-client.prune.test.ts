import { describe, it, expect, beforeEach } from 'vitest'
import { queryClient, pruneMessageScopedQueries } from './query-client'

/**
 * v0.8.66 (audit F-2) — pruneMessageScopedQueries removes the ad-hoc
 * per-message chat cache entries WITHOUT touching other queries.
 *
 * The two real per-message key families (verified against the writers in
 * useNotebookChat/useSourceChat and the readers in CitationPill +
 * ChatMessageProviderBadge/PrivacyBadge/AgentStateBadge):
 *   ['mcp', 'tool-calls', <id>]          — CitationPill MCP popover payloads
 *   ['chat', 'selected-provider', <id>]  — provider + privacy + agent-state badge
 */
describe('pruneMessageScopedQueries (F-2)', () => {
  beforeEach(() => {
    queryClient.clear()
  })

  it('removes all per-message chat/mcp badge entries', () => {
    queryClient.setQueryData(['mcp', 'tool-calls', 'msg-1'], [{ name: 't' }])
    queryClient.setQueryData(['mcp', 'tool-calls', 'msg-2'], [{ name: 't' }])
    queryClient.setQueryData(['chat', 'selected-provider', 'msg-1'], {
      selected_provider: 'local',
      privacy_gated: false,
      agent_state: 'complete',
    })
    queryClient.setQueryData(['chat', 'selected-provider', 'msg-2'], {
      selected_provider: 'cloud',
    })

    pruneMessageScopedQueries()

    expect(queryClient.getQueryData(['mcp', 'tool-calls', 'msg-1'])).toBeUndefined()
    expect(queryClient.getQueryData(['mcp', 'tool-calls', 'msg-2'])).toBeUndefined()
    expect(queryClient.getQueryData(['chat', 'selected-provider', 'msg-1'])).toBeUndefined()
    expect(queryClient.getQueryData(['chat', 'selected-provider', 'msg-2'])).toBeUndefined()
  })

  it('does NOT remove the non-ephemeral mcp web-search status or unrelated queries', () => {
    queryClient.setQueryData(['mcp', 'web-search'], { enabled: true })
    queryClient.setQueryData(['notebook-chat', 'nb-1', 'sessions'], [{ id: 's1' }])
    queryClient.setQueryData(['notebooks'], [{ id: 'nb-1' }])
    queryClient.setQueryData(['mcp', 'tool-calls', 'msg-1'], [{ name: 't' }])

    pruneMessageScopedQueries()

    // The per-message entry is gone…
    expect(queryClient.getQueryData(['mcp', 'tool-calls', 'msg-1'])).toBeUndefined()
    // …but these survive (different 2nd element / unrelated key).
    expect(queryClient.getQueryData(['mcp', 'web-search'])).toEqual({ enabled: true })
    expect(queryClient.getQueryData(['notebook-chat', 'nb-1', 'sessions'])).toEqual([{ id: 's1' }])
    expect(queryClient.getQueryData(['notebooks'])).toEqual([{ id: 'nb-1' }])
  })
})
