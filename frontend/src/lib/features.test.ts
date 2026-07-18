import { afterEach, describe, expect, it } from 'vitest'

import {
  isEvidenceStudioEnabled,
  isModelFleetEnabled,
  isResearchRunsEnabled,
  isVisualRefreshEnabled,
} from './features'

const FEATURE_ENV = [
  'NEXT_PUBLIC_ONP_VISUAL_REFRESH',
  'NEXT_PUBLIC_ONP_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_ONP_MODEL_FLEET',
  'NEXT_PUBLIC_ONP_RESEARCH_RUNS',
] as const

describe('frontend feature flags', () => {
  afterEach(() => {
    for (const name of FEATURE_ENV) {
      delete process.env[name]
    }
  })

  it('enables stable Plus surfaces by default while keeping research runs experimental', () => {
    for (const name of FEATURE_ENV) {
      delete process.env[name]
    }

    expect(isVisualRefreshEnabled()).toBe(true)
    expect(isEvidenceStudioEnabled()).toBe(true)
    expect(isModelFleetEnabled()).toBe(true)
    expect(isResearchRunsEnabled()).toBe(false)
  })

  it('parses truthy and falsey frontend flag values independently', () => {
    process.env.NEXT_PUBLIC_ONP_VISUAL_REFRESH = 'enabled'
    process.env.NEXT_PUBLIC_ONP_EVIDENCE_STUDIO = 'yes'
    process.env.NEXT_PUBLIC_ONP_MODEL_FLEET = 'on'
    process.env.NEXT_PUBLIC_ONP_RESEARCH_RUNS = '1'

    expect(isVisualRefreshEnabled()).toBe(true)
    expect(isEvidenceStudioEnabled()).toBe(true)
    expect(isModelFleetEnabled()).toBe(true)
    expect(isResearchRunsEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_ONP_MODEL_FLEET = '0'
    expect(isModelFleetEnabled()).toBe(false)

    process.env.NEXT_PUBLIC_ONP_EVIDENCE_STUDIO = 'false'
    expect(isEvidenceStudioEnabled()).toBe(false)
  })
})
