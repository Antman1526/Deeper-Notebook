const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled'])

function envFlag(
  value: string | undefined,
  defaultValue = false,
): boolean {
  return value === undefined ? defaultValue : TRUTHY.has(value.trim().toLowerCase())
}

export function isEvidenceStudioEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_EVIDENCE_STUDIO,
    true,
  )
}

export function isVisualRefreshEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_VISUAL_REFRESH,
    true,
  )
}

export function isModelFleetEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_MODEL_FLEET,
    true,
  )
}

export function isResearchRunsEnabled(): boolean {
  return envFlag(process.env.NEXT_PUBLIC_DN_RESEARCH_RUNS)
}
