import { afterEach, describe, expect, it } from 'vitest'

import {
  isEvidenceStudioEnabled,
  isLuminousFolioEnabled,
  isModelFleetEnabled,
  isResearchRunsEnabled,
  isVisualRefreshEnabled,
} from './features'

const FEATURE_ENV = [
  'NEXT_PUBLIC_DN_VISUAL_REFRESH',
  'NEXT_PUBLIC_DN_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_DN_MODEL_FLEET',
  'NEXT_PUBLIC_DN_RESEARCH_RUNS',
  'NEXT_PUBLIC_DN_LUMINOUS_FOLIO',
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

  it('enables stable Deeper Notebook surfaces by default while keeping research runs experimental', () => {
    for (const name of FEATURE_ENV) {
      delete process.env[name]
    }

    expect(isVisualRefreshEnabled()).toBe(true)
    expect(isEvidenceStudioEnabled()).toBe(true)
    expect(isModelFleetEnabled()).toBe(true)
    expect(isResearchRunsEnabled()).toBe(false)
  })

  it('keeps Luminous Folio disabled by default and reads its canonical flag', () => {
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO

    expect(isLuminousFolioEnabled()).toBe(false)

    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = 'enabled'

    expect(isLuminousFolioEnabled()).toBe(true)
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

  it('continues to support legacy Plus flags when canonical flags are absent', () => {
    process.env.NEXT_PUBLIC_ONP_VISUAL_REFRESH = '0'
    process.env.NEXT_PUBLIC_ONP_EVIDENCE_STUDIO = 'false'
    process.env.NEXT_PUBLIC_ONP_MODEL_FLEET = 'no'
    process.env.NEXT_PUBLIC_ONP_RESEARCH_RUNS = 'enabled'

    expect(isVisualRefreshEnabled()).toBe(false)
    expect(isEvidenceStudioEnabled()).toBe(false)
    expect(isModelFleetEnabled()).toBe(false)
    expect(isResearchRunsEnabled()).toBe(true)
  })

  it('gives canonical Deeper Notebook flags precedence over legacy Plus flags', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_REFRESH = '0'
    process.env.NEXT_PUBLIC_DN_EVIDENCE_STUDIO = 'false'
    process.env.NEXT_PUBLIC_DN_MODEL_FLEET = 'no'
    process.env.NEXT_PUBLIC_DN_RESEARCH_RUNS = 'enabled'
    process.env.NEXT_PUBLIC_ONP_VISUAL_REFRESH = 'enabled'
    process.env.NEXT_PUBLIC_ONP_EVIDENCE_STUDIO = 'yes'
    process.env.NEXT_PUBLIC_ONP_MODEL_FLEET = 'on'
    process.env.NEXT_PUBLIC_ONP_RESEARCH_RUNS = '0'

    expect(isVisualRefreshEnabled()).toBe(false)
    expect(isEvidenceStudioEnabled()).toBe(false)
    expect(isModelFleetEnabled()).toBe(false)
    expect(isResearchRunsEnabled()).toBe(true)
  })

})
