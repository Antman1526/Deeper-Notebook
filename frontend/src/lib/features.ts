import { useSyncExternalStore } from 'react'

const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled'])

// v0.8.107 — runtime overrides for build-time flags.
//
// NEXT_PUBLIC_* values are INLINED by Next at build time, so a packaged .app has
// its UI feature set frozen in the bundle. Turning a feature off server-side
// left its buttons rendered and dead, because the client never learned the
// backend had stopped supporting it (§4.3 of PROJECT-DEEP-DIVE; it is what
// produced the dead Refresh/Remove controls in the source gallery).
//
// `applyRuntimeFeatures` lets the client adopt the backend's answer from
// GET /api/features at boot. The inlined value remains the DEFAULT, so:
//   * before the fetch resolves, behaviour is exactly as it is today;
//   * if the endpoint is unreachable or the backend predates it, nothing
//     changes — this can only ever correct a flag, never strand the UI.
let runtimeOverrides: Partial<Record<FeatureName, boolean>> = {}
const runtimeFeatureListeners = new Set<() => void>()

export type FeatureName =
  | 'evidenceStudio'
  | 'visualRefresh'
  | 'modelFleet'
  | 'researchRuns'
  | 'studyWorkbench'
  | 'sourceVisuals'

const FEATURE_NAMES = new Set<FeatureName>([
  'evidenceStudio',
  'visualRefresh',
  'modelFleet',
  'researchRuns',
  'studyWorkbench',
  'sourceVisuals',
])

export function applyRuntimeFeatures(features: unknown): void {
  if (!features || typeof features !== 'object') return
  const next: Partial<Record<FeatureName, boolean>> = {}
  for (const [key, value] of Object.entries(features as Record<string, unknown>)) {
    // Only booleans are adopted. A malformed payload must not flip a flag to a
    // truthy string, which is the failure mode that would silently re-enable a
    // rolled-back feature.
    if (isFeatureName(key) && typeof value === 'boolean') next[key] = value
  }

  if (sameRuntimeOverrides(runtimeOverrides, next)) return
  runtimeOverrides = next
  notifyRuntimeFeatureListeners()
}

export function resetRuntimeFeatures(): void {
  if (Object.keys(runtimeOverrides).length === 0) return
  runtimeOverrides = {}
  notifyRuntimeFeatureListeners()
}

export function subscribeRuntimeFeatures(listener: () => void): () => void {
  runtimeFeatureListeners.add(listener)
  return () => runtimeFeatureListeners.delete(listener)
}

function sameRuntimeOverrides(
  left: Partial<Record<FeatureName, boolean>>,
  right: Partial<Record<FeatureName, boolean>>,
): boolean {
  const leftEntries = Object.entries(left)
  return leftEntries.length === Object.keys(right).length
    && leftEntries.every(([key, value]) => right[key as FeatureName] === value)
}

function notifyRuntimeFeatureListeners(): void {
  runtimeFeatureListeners.forEach(listener => listener())
}

function isFeatureName(key: string): key is FeatureName {
  return FEATURE_NAMES.has(key as FeatureName)
}

function resolve(name: FeatureName, inlinedDefault: boolean): boolean {
  const override = runtimeOverrides[name]
  return override === undefined ? inlinedDefault : override
}

function envFlag(
  canonicalValue: string | undefined,
  legacyValue: string | undefined,
  defaultValue = false,
): boolean {
  const value = canonicalValue ?? legacyValue
  return value === undefined ? defaultValue : TRUTHY.has(value.trim().toLowerCase())
}

export function isEvidenceStudioEnabled(): boolean {
  return resolve('evidenceStudio', envFlag(
    process.env.NEXT_PUBLIC_DN_EVIDENCE_STUDIO,
    process.env.NEXT_PUBLIC_ONP_EVIDENCE_STUDIO,
    true,
  ))
}

export function isVisualRefreshEnabled(): boolean {
  return resolve('visualRefresh', envFlag(
    process.env.NEXT_PUBLIC_DN_VISUAL_REFRESH,
    process.env.NEXT_PUBLIC_ONP_VISUAL_REFRESH,
    true,
  ))
}

export function isModelFleetEnabled(): boolean {
  return resolve('modelFleet', envFlag(
    process.env.NEXT_PUBLIC_DN_MODEL_FLEET,
    process.env.NEXT_PUBLIC_ONP_MODEL_FLEET,
    true,
  ))
}

export function isResearchRunsEnabled(): boolean {
  return resolve('researchRuns', envFlag(
    process.env.NEXT_PUBLIC_DN_RESEARCH_RUNS,
    process.env.NEXT_PUBLIC_ONP_RESEARCH_RUNS,
  ))
}

export function isStudyWorkbenchEnabled(): boolean {
  return resolve('studyWorkbench', envFlag(process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH, undefined, true))
}

export function isLuminousFolioEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO,
    undefined,
    true,
  )
}

export function isVisualSystemV2Enabled(): boolean {
  return envFlag(process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2, undefined, true)
}

export function isSourceVisualsEnabled(): boolean {
  return resolve('sourceVisuals', envFlag(process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS, undefined, true))
}

export function useSourceVisualsEnabled(): boolean {
  return useSyncExternalStore(
    subscribeRuntimeFeatures,
    isSourceVisualsEnabled,
    isSourceVisualsEnabled,
  )
}
