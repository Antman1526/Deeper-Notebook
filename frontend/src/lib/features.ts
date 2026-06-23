const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled'])

function envFlag(name: string, defaultValue = false): boolean {
  const value = process.env[name]
  return value ? TRUTHY.has(value.trim().toLowerCase()) : defaultValue
}

export function isEvidenceStudioEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_ONP_EVIDENCE_STUDIO', true)
}

export function isVisualRefreshEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_ONP_VISUAL_REFRESH', true)
}

export function isModelFleetEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_ONP_MODEL_FLEET', true)
}

export function isResearchRunsEnabled(): boolean {
  return envFlag('NEXT_PUBLIC_ONP_RESEARCH_RUNS')
}
