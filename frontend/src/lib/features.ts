const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled'])

function envFlag(
  canonicalValue: string | undefined,
  legacyValue: string | undefined,
  defaultValue = false,
): boolean {
  const value = canonicalValue ?? legacyValue
  return value === undefined ? defaultValue : TRUTHY.has(value.trim().toLowerCase())
}

export function isEvidenceStudioEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_EVIDENCE_STUDIO,
    process.env.NEXT_PUBLIC_ONP_EVIDENCE_STUDIO,
    true,
  )
}

export function isVisualRefreshEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_VISUAL_REFRESH,
    process.env.NEXT_PUBLIC_ONP_VISUAL_REFRESH,
    true,
  )
}

export function isModelFleetEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_MODEL_FLEET,
    process.env.NEXT_PUBLIC_ONP_MODEL_FLEET,
    true,
  )
}

export function isResearchRunsEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_RESEARCH_RUNS,
    process.env.NEXT_PUBLIC_ONP_RESEARCH_RUNS,
  )
}

export function isLuminousFolioEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO,
    undefined,
    false,
  )
}
