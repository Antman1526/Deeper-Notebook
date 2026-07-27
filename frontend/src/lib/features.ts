const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled'])

function envFlag(canonicalName: string, legacyName: string, defaultValue = false): boolean {
  const value = process.env[canonicalName] ?? process.env[legacyName]
  return value === undefined ? defaultValue : TRUTHY.has(value.trim().toLowerCase())
}

export function isEvidenceStudioEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_DN_EVIDENCE_STUDIO', 'NEXT_PUBLIC_ONP_EVIDENCE_STUDIO', true)
}

export function isVisualRefreshEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_DN_VISUAL_REFRESH', 'NEXT_PUBLIC_ONP_VISUAL_REFRESH', true)
}

export function isModelFleetEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_DN_MODEL_FLEET', 'NEXT_PUBLIC_ONP_MODEL_FLEET', true)
}

export function isResearchRunsEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_DN_RESEARCH_RUNS', 'NEXT_PUBLIC_ONP_RESEARCH_RUNS')
}
