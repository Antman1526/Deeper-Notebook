import type { TFunction } from 'i18next'
import { describe, expect, it } from 'vitest'

import {
  getResearchModeAvailability,
  RESEARCH_MODE_DESCRIPTORS,
  RESEARCH_MODE_ICON_KEYS,
} from './research-modes'

// Identity translator: assertions below expect the i18n key, not the English.
const t = ((key: string) => key) as unknown as TFunction

describe('research mode descriptors', () => {
  it.each([
    ['read', 'knowledge.commands.modeRead', 'book-open', '1', 'document'],
    ['write', 'knowledge.commands.modeWrite', 'file-pen-line', '2', 'document'],
    ['ask', 'knowledge.commands.modeAsk', 'message-circle-question', '3', 'ask'],
    ['search', 'knowledge.commands.modeSearch', 'search', '4', 'search'],
    ['graph', 'knowledge.commands.modeGraph', 'network', '5', 'graph'],
    ['podcast', 'knowledge.commands.modePodcast', 'podcast', '6', 'podcast'],
  ] as const)('describes %s with its stable launcher metadata', (id, labelKey, iconKey, shortcut, targetKind) => {
    expect(RESEARCH_MODE_DESCRIPTORS[id]).toMatchObject({ id, labelKey, shortcut, targetKind })
    expect(RESEARCH_MODE_ICON_KEYS[id]).toBe(iconKey)
    expect(getResearchModeAvailability(id, {
      target: targetKind === 'document'
        ? { kind: 'document', authority: 'overlay' }
        : { kind: targetKind },
      t,
    })).toEqual({ available: true, reason: null })
  })

  it('keeps external documents read only and returns the local readiness reason for Ask', () => {
    expect(getResearchModeAvailability('write', {
      target: { kind: 'document', authority: 'external-vault' },
      t,
    })).toEqual({ available: false, reason: 'knowledge.researchModes.externalReadOnly' })

    expect(getResearchModeAvailability('ask', {
      target: { kind: 'ask' },
      askReadinessReason: 'Local research model is unavailable',
      t,
    })).toEqual({ available: false, reason: 'Local research model is unavailable' })
  })

  it('allows Search without a current document selection', () => {
    expect(getResearchModeAvailability('search', {
      target: { kind: 'search' },
      t,
    })).toEqual({ available: true, reason: null })
  })

  it('fails closed when a target is missing or incompatible', () => {
    expect(getResearchModeAvailability('ask', { t })).toEqual({
      available: false,
      reason: 'knowledge.researchModes.requiresTarget',
    })
    expect(getResearchModeAvailability('podcast', { target: { kind: 'search' }, t })).toEqual({
      available: false,
      reason: 'knowledge.researchModes.requiresTarget',
    })
  })
})
