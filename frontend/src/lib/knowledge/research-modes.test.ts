import { describe, expect, it } from 'vitest'

import {
  getResearchModeAvailability,
  RESEARCH_MODE_DESCRIPTORS,
  RESEARCH_MODE_ICON_KEYS,
} from './research-modes'

describe('research mode descriptors', () => {
  it.each([
    ['read', 'Read', 'book-open', '1', 'document'],
    ['write', 'Write', 'file-pen-line', '2', 'document'],
    ['ask', 'Ask', 'message-circle-question', '3', 'ask'],
    ['search', 'Search', 'search', '4', 'search'],
    ['graph', 'Graph', 'network', '5', 'graph'],
    ['podcast', 'Podcast', 'podcast', '6', 'podcast'],
  ] as const)('describes %s with its stable launcher metadata', (id, label, iconKey, shortcut, targetKind) => {
    expect(RESEARCH_MODE_DESCRIPTORS[id]).toMatchObject({ id, label, shortcut, targetKind })
    expect(RESEARCH_MODE_ICON_KEYS[id]).toBe(iconKey)
    expect(getResearchModeAvailability(id, {
      target: targetKind === 'document'
        ? { kind: 'document', authority: 'overlay' }
        : { kind: targetKind },
    })).toEqual({ available: true, reason: null })
  })

  it('keeps external documents read only and returns the local readiness reason for Ask', () => {
    expect(getResearchModeAvailability('write', {
      target: { kind: 'document', authority: 'external-vault' },
    })).toEqual({ available: false, reason: 'External source — read only' })

    expect(getResearchModeAvailability('ask', {
      target: { kind: 'ask' },
      askReadinessReason: 'Local research model is unavailable',
    })).toEqual({ available: false, reason: 'Local research model is unavailable' })
  })

  it('allows Search without a current document selection', () => {
    expect(getResearchModeAvailability('search', {
      target: { kind: 'search' },
    })).toEqual({ available: true, reason: null })
  })
})
