import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  applyRuntimeFeatures,
  resetRuntimeFeatures,
  isEvidenceStudioEnabled,
  isLuminousFolioEnabled,
  isModelFleetEnabled,
  isResearchRunsEnabled,
  isSourceVisualsEnabled,
  isStudyWorkbenchEnabled,
  isVisualSystemV2Enabled,
  isVisualRefreshEnabled,
  subscribeRuntimeFeatures,
} from './features'

const FEATURE_ENV = [
  'NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2',
  'NEXT_PUBLIC_DN_SOURCE_VISUALS',
  'NEXT_PUBLIC_DN_VISUAL_REFRESH',
  'NEXT_PUBLIC_DN_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_DN_MODEL_FLEET',
  'NEXT_PUBLIC_DN_RESEARCH_RUNS',
  'NEXT_PUBLIC_DN_STUDY_WORKBENCH',
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

  it('enables Luminous Folio by default and keeps its canonical rollback flag', () => {
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO

    expect(isLuminousFolioEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '0'

    expect(isLuminousFolioEnabled()).toBe(false)
  })

  it('enables the Gemini-forward visual system by default while retaining its canonical rollback flag', () => {
    delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
    expect(isVisualSystemV2Enabled()).toBe(true)

    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '1'
    expect(isVisualSystemV2Enabled()).toBe(true)

    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '0'
    expect(isVisualSystemV2Enabled()).toBe(false)
  })

  it('enables source visuals by default while retaining its canonical rollback flag', () => {
    delete process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS
    expect(isSourceVisualsEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '1'
    expect(isSourceVisualsEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '0'
    expect(isSourceVisualsEnabled()).toBe(false)
  })

  it('enables the Study Workbench by default and accepts its canonical rollback flag', () => {
    delete process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH

    expect(isStudyWorkbenchEnabled()).toBe(true)

    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '0'

    expect(isStudyWorkbenchEnabled()).toBe(false)
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

// v0.8.107 — runtime overrides for build-time flags.
describe('runtime feature overrides', () => {
  afterEach(() => {
    resetRuntimeFeatures()
  })

  it('leaves the inlined default in place until a payload arrives', () => {
    // The pre-fetch state must be today's behaviour exactly — otherwise every
    // packaged build flickers its UI on boot.
    resetRuntimeFeatures()
    expect(isStudyWorkbenchEnabled()).toBe(true)
  })

  it('adopts the backend answer over the inlined default', () => {
    applyRuntimeFeatures({ studyWorkbench: false })
    expect(isStudyWorkbenchEnabled()).toBe(false)
  })

  it('allows the backend runtime response to roll source visuals back below the inlined default', () => {
    expect(isSourceVisualsEnabled()).toBe(true)
    applyRuntimeFeatures({ sourceVisuals: false })
    expect(isSourceVisualsEnabled()).toBe(false)
  })

  it('preserves the last runtime rollback when a later source-visual value is malformed', () => {
    applyRuntimeFeatures({ sourceVisuals: false })
    applyRuntimeFeatures({ sourceVisuals: 'false' })

    expect(isSourceVisualsEnabled()).toBe(false)
  })

  it('preserves the last runtime rollback when a later payload contains only unknown features', () => {
    applyRuntimeFeatures({ sourceVisuals: false })
    applyRuntimeFeatures({ unknownFeature: true })

    expect(isSourceVisualsEnabled()).toBe(false)
  })

  it('rejects mixed valid and malformed payloads atomically', () => {
    applyRuntimeFeatures({ sourceVisuals: false })
    applyRuntimeFeatures({ sourceVisuals: true, visualRefresh: 'false' })

    expect(isSourceVisualsEnabled()).toBe(false)
  })

  it('ignores non-boolean values rather than coercing them', () => {
    // A truthy string here would silently re-enable a rolled-back feature,
    // which is the precise failure this layer exists to prevent.
    applyRuntimeFeatures({ studyWorkbench: 'false', sourceVisuals: 'yes' })
    expect(isStudyWorkbenchEnabled()).toBe(true)
    expect(isSourceVisualsEnabled()).toBe(true)
  })

  it('ignores a malformed payload entirely', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeRuntimeFeatures(listener)

    applyRuntimeFeatures(null)
    applyRuntimeFeatures('nope')
    applyRuntimeFeatures({ sourceVisuals: 'false' })
    applyRuntimeFeatures({ unknownFeature: true })

    expect(isStudyWorkbenchEnabled()).toBe(true)
    expect(listener).not.toHaveBeenCalled()

    unsubscribe()
  })

  it('only overrides the keys it was given', () => {
    applyRuntimeFeatures({ sourceVisuals: true })
    expect(isSourceVisualsEnabled()).toBe(true)
    expect(isStudyWorkbenchEnabled()).toBe(true)
  })

  it('notifies active readers once per runtime change and releases unsubscribed readers', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeRuntimeFeatures(listener)

    applyRuntimeFeatures({ sourceVisuals: false })
    applyRuntimeFeatures({ sourceVisuals: false })

    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    applyRuntimeFeatures({ sourceVisuals: true })

    expect(listener).toHaveBeenCalledTimes(1)
  })
})
