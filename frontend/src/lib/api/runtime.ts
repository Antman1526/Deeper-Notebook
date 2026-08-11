import apiClient from './client'

export type RuntimeState = 'ready' | 'degraded' | 'unknown'
export type RuntimeDatabaseState = 'online' | 'offline' | 'unknown'
export type RuntimeMigrationState = 'applied' | 'pending' | 'unknown'
export type RuntimeBackupFreshness = 'valid' | 'stale' | 'unknown'
export type RuntimeBackupIntegrity = 'verified' | 'unknown'
export type RuntimeFingerprintState = 'available' | 'unknown'

export type RuntimeReasonCode =
  | 'readiness_unknown'
  | 'database_offline'
  | 'database_check_failed'
  | 'migrations_pending'
  | 'migrations_check_failed'
  | 'vault_degraded'
  | 'vault_unavailable'
  | 'vault_unknown'
  | 'knowledge_degraded'
  | 'knowledge_unknown'
  | 'startup_receipt_unavailable'
  | 'startup_receipt_invalid'
  | 'updates_disabled'
  | 'updates_unknown'
  | 'auto_export_unknown'
  | 'auto_export_stale'
  | 'provenance_unknown'

const RUNTIME_STATES = new Set<RuntimeState>(['ready', 'degraded', 'unknown'])
const DATABASE_STATES = new Set<RuntimeDatabaseState>(['online', 'offline', 'unknown'])
const MIGRATION_STATES = new Set<RuntimeMigrationState>(['applied', 'pending', 'unknown'])
const REASON_CODES = new Set<RuntimeReasonCode>([
  'readiness_unknown',
  'database_offline',
  'database_check_failed',
  'migrations_pending',
  'migrations_check_failed',
  'vault_degraded',
  'vault_unavailable',
  'vault_unknown',
  'knowledge_degraded',
  'knowledge_unknown',
  'startup_receipt_unavailable',
  'startup_receipt_invalid',
  'updates_disabled',
  'updates_unknown',
  'auto_export_unknown',
  'auto_export_stale',
  'provenance_unknown',
])
const STARTUP_STAGES = new Set([
  'launcher_start',
  'chat_model_cache_hit',
  'chat_model_scan',
  'core_ready',
])
// Keep the wire cap stable as the allowlist grows; a malformed provider must
// never expand the cached response's repeated-field budget.
const MAX_RUNTIME_REASONS = 15
const MAX_STARTUP_STAGES = 16
const VERSION_PATTERN = /^v?[0-9]+(?:\.[0-9]+){0,4}(?:[-+][A-Za-z0-9.-]{1,16})?$/

export interface RuntimeReadiness {
  state: RuntimeState
  database: RuntimeDatabaseState
  migrations: RuntimeMigrationState
}

export interface RuntimeStartupStage {
  stage: 'launcher_start' | 'chat_model_cache_hit' | 'chat_model_scan' | 'core_ready'
  elapsed_ms: number
}

export interface RuntimeStartup {
  state: RuntimeState
  stages: RuntimeStartupStage[]
}

export interface RuntimeUpdates {
  state: RuntimeState
  enabled: boolean | null
  update_available: boolean | null
  current_version: string | null
}

export interface RuntimeVault {
  state: RuntimeState
  ready: number
  degraded: number
  unavailable: number
}

export interface RuntimeKnowledge {
  state: RuntimeState
  projected: number | null
  unchanged: number | null
  failed: number | null
}

export interface RuntimeBackup {
  state: RuntimeState
  freshness?: RuntimeBackupFreshness
  integrity?: RuntimeBackupIntegrity
  file_count: number
  newest_age_seconds: number | null
  newest_size_bytes?: number | null
  newest_timestamp?: string | null
}

export interface RuntimeProvenance {
  state: RuntimeState
  mount_count: number
  external_read_only_count: number
  source_fingerprint_state: RuntimeFingerprintState
}

export interface RuntimeSnapshot {
  schema_version: 'runtime-snapshot-v1'
  status: RuntimeState
  reasons: RuntimeReasonCode[]
  readiness: RuntimeReadiness
  startup: RuntimeStartup
  updates: RuntimeUpdates
  vault: RuntimeVault
  knowledge: RuntimeKnowledge
  backup: RuntimeBackup
  provenance?: RuntimeProvenance
}

export const UNKNOWN_RUNTIME_SNAPSHOT: RuntimeSnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'unknown',
  reasons: ['readiness_unknown'],
  readiness: { state: 'unknown', database: 'unknown', migrations: 'unknown' },
  startup: { state: 'unknown', stages: [] },
  updates: { state: 'unknown', enabled: null, update_available: null, current_version: null },
  vault: { state: 'unknown', ready: 0, degraded: 0, unavailable: 0 },
  knowledge: { state: 'unknown', projected: null, unchanged: null, failed: null },
  backup: {
    state: 'unknown',
    freshness: 'unknown',
    integrity: 'unknown',
    file_count: 0,
    newest_age_seconds: null,
    newest_size_bytes: null,
    newest_timestamp: null,
  },
  provenance: {
    state: 'unknown',
    mount_count: 0,
    external_read_only_count: 0,
    source_fingerprint_state: 'unknown',
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNullableBoolean(value: unknown): value is boolean | null {
  return value === null || typeof value === 'boolean'
}

function isNullableBoundedCount(value: unknown, max = 1_000_000): value is number | null {
  return value === null || (
    typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max
  )
}

function isSafeTimestamp(value: unknown): value is string | null | undefined {
  return value === undefined || value === null || (
    typeof value === 'string'
    && value.length <= 40
    && !Number.isNaN(Date.parse(value))
  )
}

function isSafeVersion(value: unknown): value is string | null {
  return value === null || (
    typeof value === 'string' && value.length <= 32 && VERSION_PATTERN.test(value)
  )
}

function isReadiness(value: unknown): value is RuntimeReadiness {
  if (!isRecord(value)) return false
  return (
    RUNTIME_STATES.has(value.state as RuntimeState) &&
    DATABASE_STATES.has(value.database as RuntimeDatabaseState) &&
    MIGRATION_STATES.has(value.migrations as RuntimeMigrationState)
  )
}

function isStartup(value: unknown): value is RuntimeStartup {
  if (
    !isRecord(value)
    || !RUNTIME_STATES.has(value.state as RuntimeState)
    || !Array.isArray(value.stages)
    || value.stages.length > MAX_STARTUP_STAGES
  ) {
    return false
  }
  return value.stages.every((stage) => {
    if (!isRecord(stage) || !STARTUP_STAGES.has(stage.stage as string)) return false
    return typeof stage.elapsed_ms === 'number' && Number.isInteger(stage.elapsed_ms)
      && stage.elapsed_ms >= 0 && stage.elapsed_ms <= 86_400_000
  })
}

function isUpdates(value: unknown): value is RuntimeUpdates {
  if (!isRecord(value) || !RUNTIME_STATES.has(value.state as RuntimeState)) return false
  return isNullableBoolean(value.enabled)
    && isNullableBoolean(value.update_available)
    && isSafeVersion(value.current_version)
}

function isVault(value: unknown): value is RuntimeVault {
  if (!isRecord(value) || !RUNTIME_STATES.has(value.state as RuntimeState)) return false
  return [value.ready, value.degraded, value.unavailable].every((count) =>
    typeof count === 'number' && Number.isInteger(count) && count >= 0 && count <= 1_000_000,
  )
}

function isKnowledge(value: unknown): value is RuntimeKnowledge {
  if (!isRecord(value) || !RUNTIME_STATES.has(value.state as RuntimeState)) return false
  return isNullableBoundedCount(value.projected)
    && isNullableBoundedCount(value.unchanged)
    && isNullableBoundedCount(value.failed)
}

function isBackup(value: unknown): value is RuntimeBackup {
  if (!isRecord(value) || !RUNTIME_STATES.has(value.state as RuntimeState)) return false
  if (
    value.freshness !== undefined
    && !new Set<RuntimeBackupFreshness>(['valid', 'stale', 'unknown']).has(
      value.freshness as RuntimeBackupFreshness,
    )
  ) return false
  if (
    value.integrity !== undefined
    && !new Set<RuntimeBackupIntegrity>(['verified', 'unknown']).has(
      value.integrity as RuntimeBackupIntegrity,
    )
  ) return false
  return typeof value.file_count === 'number'
    && Number.isInteger(value.file_count)
    && value.file_count >= 0
    && value.file_count <= 64
    && isNullableBoundedCount(value.newest_age_seconds, 31_536_000_000)
    && (value.newest_size_bytes === undefined
      || isNullableBoundedCount(value.newest_size_bytes, 4_294_967_296))
    && isSafeTimestamp(value.newest_timestamp)
}

function isProvenance(value: unknown): value is RuntimeProvenance {
  if (!isRecord(value) || !RUNTIME_STATES.has(value.state as RuntimeState)) return false
  return typeof value.mount_count === 'number'
    && Number.isInteger(value.mount_count)
    && value.mount_count >= 0
    && value.mount_count <= 1_000_000
    && typeof value.external_read_only_count === 'number'
    && Number.isInteger(value.external_read_only_count)
    && value.external_read_only_count >= 0
    && value.external_read_only_count <= 1_000_000
    && (value.source_fingerprint_state === 'available' || value.source_fingerprint_state === 'unknown')
}

export function isRuntimeSnapshot(value: unknown): value is RuntimeSnapshot {
  if (!isRecord(value) || value.schema_version !== 'runtime-snapshot-v1') return false
  if (!RUNTIME_STATES.has(value.status as RuntimeState)) return false
  if (
    !Array.isArray(value.reasons)
    || value.reasons.length > MAX_RUNTIME_REASONS
    || !value.reasons.every((reason) => REASON_CODES.has(reason as RuntimeReasonCode))
  ) {
    return false
  }
  return isReadiness(value.readiness)
    && isStartup(value.startup)
    && isUpdates(value.updates)
    && isVault(value.vault)
    && isKnowledge(value.knowledge)
    && isBackup(value.backup)
    && (value.provenance === undefined || isProvenance(value.provenance))
}

export function normalizeRuntimeSnapshot(value: unknown): RuntimeSnapshot {
  try {
    if (!isRuntimeSnapshot(value)) return UNKNOWN_RUNTIME_SNAPSHOT

    const reasons: RuntimeReasonCode[] = []
    for (const reason of value.reasons) {
      if (!reasons.includes(reason)) reasons.push(reason)
    }

    const backup: RuntimeBackup = {
      state: value.backup.state,
      file_count: value.backup.file_count,
      newest_age_seconds: value.backup.newest_age_seconds,
    }
    if (value.backup.freshness !== undefined) backup.freshness = value.backup.freshness
    if (value.backup.integrity !== undefined) backup.integrity = value.backup.integrity
    if (value.backup.newest_size_bytes !== undefined) {
      backup.newest_size_bytes = value.backup.newest_size_bytes
    }
    if (value.backup.newest_timestamp !== undefined) {
      backup.newest_timestamp = value.backup.newest_timestamp
    }

    return {
      schema_version: 'runtime-snapshot-v1',
      status: value.status,
      reasons,
      readiness: {
        state: value.readiness.state,
        database: value.readiness.database,
        migrations: value.readiness.migrations,
      },
      startup: {
        state: value.startup.state,
        stages: value.startup.stages.map((stage) => ({
          stage: stage.stage,
          elapsed_ms: stage.elapsed_ms,
        })),
      },
      updates: {
        state: value.updates.state,
        enabled: value.updates.enabled,
        update_available: value.updates.update_available,
        current_version: value.updates.current_version,
      },
      vault: {
        state: value.vault.state,
        ready: value.vault.ready,
        degraded: value.vault.degraded,
        unavailable: value.vault.unavailable,
      },
      knowledge: {
        state: value.knowledge.state,
        projected: value.knowledge.projected,
        unchanged: value.knowledge.unchanged,
        failed: value.knowledge.failed,
      },
      backup,
      ...(value.provenance ? {
        provenance: {
          state: value.provenance.state,
          mount_count: value.provenance.mount_count,
          external_read_only_count: value.provenance.external_read_only_count,
          source_fingerprint_state: value.provenance.source_fingerprint_state,
        },
      } : {}),
    }
  } catch {
    return UNKNOWN_RUNTIME_SNAPSHOT
  }
}

export const runtimeApi = {
  async getSnapshot(): Promise<RuntimeSnapshot> {
    try {
      const { data } = await apiClient.get<unknown>('/runtime/snapshot')
      return normalizeRuntimeSnapshot(data)
    } catch {
      return UNKNOWN_RUNTIME_SNAPSHOT
    }
  },
}
