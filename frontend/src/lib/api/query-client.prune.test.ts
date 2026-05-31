import { describe, it, expect, beforeEach } from 'vitest'
import { queryClient, pruneMessageScopedQueries } from './query-client'

/**
 * v0.8.66 (audit F-2) — pruneMessageScopedQueries removes the ad-hoc
 * per-message chat cache entries (mcp tool-calls + provider/privacy/agent-state
 * badges) so they don't accumulate, WITHOUT touching other queries.
 */
describe('pruneMessageScopedQueries (F-2)', () => {
  beforeEach(() => {
    queryClient.clear()
  })

  it('removes all per-message chat/mcp badge entries', () => {
    queryClient.setQueryData(['mcp', 'tool-calls', 'msg-1'], [{ name: 't' }])
    queryClient.setQueryData(['mcp', 'tool-calls', 'msg-2'], [{ name: 't' }])
    queryClient.setQueryData(['chat', 'provider', 'msg-1'], 'local')
    queryClient.setQueryData(['chat', 'privacy', 'msg-1'], { gated: false })
    queryClient.setQueryData(['chat', 'agent-state', 'msg-1'], 'complete')

    pruneMessageScopedQueries()

    expect(queryClient.getQueryData(['mcp', 'tool-calls', 'msg-1'])).toBeUndefined()
    expect(queryClient.getQueryData(['mcp', 'tool-calls', 'msg-2'])).toBeUndefined()
    expect(queryClient.getQueryData(['chat', 'provider', 'msg-1'])).toBeUndefined()
    expect(queryClient.getQueryData(['chat', 'privacy', 'msg-1'])).toBeUndefined()
    expect(queryClient.getQueryData(['chat', 'agent-state', 'msg-1'])).toBeUndefined()
  })

  it('does NOT remove the non-ephemeral mcp web-search status or unrelated queries', () => {
    queryClient.setQueryData(['mcp', 'web-search'], { enabled: true })
    queryClient.setQueryData(['chat', 'sessions', 'nb-1'], [{ id: 's1' }])
    queryClient.setQueryData(['notebooks'], [{ id: 'nb-1' }])
    queryClient.setQueryData(['mcp', 'tool-calls', 'msg-1'], [{ name: 't' }])

    pruneMessageScopedQueries()

    // The per-message entry is gone…
    expect(queryClient.getQueryData(['mcp', 'tool-calls', 'msg-1'])).toBeUndefined()
    // …but these survive (different 2nd element / unrelated key).
    expect(queryClient.getQueryData(['mcp', 'web-search'])).toEqual({ enabled: true })
    expect(queryClient.getQueryData(['chat', 'sessions', 'nb-1'])).toEqual([{ id: 's1' }])
    expect(queryClient.getQueryData(['notebooks'])).toEqual([{ id: 'nb-1' }])
  })
})
