import { afterEach, describe, expect, it } from 'vitest'

import {
  isEvidenceStudioEnabled,
  isModelFleetEnabled,
  isResearchRunsEnabled,
  isVisualRefreshEnabled,
} from './features'

const FEATURE_ENV = [
  'NEXT_PUBLIC_DN_VISUAL_REFRESH',
  'NEXT_PUBLIC_DN_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_DN_MODEL_FLEET',
  'NEXT_PUBLIC_DN_RESEARCH_RUNS',
] as const

describe('frontend feature flags', () => {
  afterEach(() => {
    for (const name of FEATURE_ENV) {
      delete process.env[name]
    }
  })

  it('enables stable Deeper Notebook surfaces by default while keeping research runs experimental', () => {
    for (const name of FEATURE_ENV) {
      delete process.env[name]
    }

    expect(isVisualRefreshEnabled()).toBe(true)
    expect(isEvidenceStudioEnabled()).toBe(true)
    expect(isModelFleetEnabled()).toBe(true)
    expect(isResearchRunsEnabled()).toBe(false)
  })

  it('reads canonical Deeper Notebook flags independently', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_REFRESH = '0'
    process.env.NEXT_PUBLIC_DN_EVIDENCE_STUDIO = 'false'
    process.env.NEXT_PUBLIC_DN_MODEL_FLEET = 'no'
    process.env.NEXT_PUBLIC_DN_RESEARCH_RUNS = 'enabled'

    expect(isVisualRefreshEnabled()).toBe(false)
    expect(isEvidenceStudioEnabled()).toBe(false)
    expect(isModelFleetEnabled()).toBe(false)
    expect(isResearchRunsEnabled()).toBe(true)
  })

})
