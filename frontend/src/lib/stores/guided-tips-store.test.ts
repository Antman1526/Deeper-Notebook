import { beforeEach, describe, expect, it } from 'vitest'

import { useGuidedTipsStore } from './guided-tips-store'

describe('guided tips store', () => {
  beforeEach(() => {
    localStorage.clear()
    useGuidedTipsStore.setState({ enabled: true, completed: {} })
  })

  it('tracks completion by the latest completed tip version', () => {
    const tip = { id: 'knowledge-overview', version: 1 }

    expect(useGuidedTipsStore.getState().isComplete(tip)).toBe(false)
    useGuidedTipsStore.getState().complete(tip)
    expect(useGuidedTipsStore.getState().isComplete(tip)).toBe(true)
    expect(useGuidedTipsStore.getState().isComplete({ ...tip, version: 2 })).toBe(false)
  })

  it('replays tips without changing the enabled preference', () => {
    const tip = { id: 'knowledge-overview', version: 1 }

    useGuidedTipsStore.getState().complete(tip)
    useGuidedTipsStore.getState().setEnabled(false)
    useGuidedTipsStore.getState().replayAll()

    expect(useGuidedTipsStore.getState().enabled).toBe(false)
    expect(useGuidedTipsStore.getState().completed).toEqual({})
  })
})
