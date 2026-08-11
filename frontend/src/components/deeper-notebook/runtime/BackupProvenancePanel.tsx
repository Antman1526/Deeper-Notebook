'use client'

import * as React from 'react'

import {
  normalizeRuntimeSnapshot,
  type RuntimeBackupFreshness,
} from '@/lib/api/runtime'

export interface BackupProvenancePanelProps {
  /** Optional fixture/presentation input; malformed values fail closed. */
  snapshot?: unknown
}

const FRESHNESS_LABELS: Record<RuntimeBackupFreshness, string> = {
  valid: 'Valid',
  stale: 'Stale',
  unknown: 'Unknown',
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'Unknown size'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`
  if (value < 1024 * 1024 * 1024) return `${Math.round(value / (1024 * 1024))} MB`
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function formatAge(value: number | null): string {
  if (value === null) return 'Unknown age'
  if (value < 60) return `${value} seconds ago`
  if (value < 3600) return `${Math.floor(value / 60)} minutes ago`
  if (value < 86_400) return `${Math.floor(value / 3600)} hours ago`
  return `${Math.floor(value / 86_400)} days ago`
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Unknown timestamp'
  try {
    return new Date(value).toISOString()
  } catch {
    return 'Unknown timestamp'
  }
}

function backupMessage(freshness: RuntimeBackupFreshness): string {
  if (freshness === 'valid') return 'A recent local backup receipt is available'
  if (freshness === 'stale') return 'Backup is older than the local retention window'
  return 'No local backup receipt is available'
}

function provenanceMessage(state: string, count: number): string {
  if (state === 'unknown') return 'External read-only provenance is unavailable'
  return `${count} external read-only ${count === 1 ? 'space' : 'spaces'}`
}

export function BackupProvenancePanel({ snapshot }: BackupProvenancePanelProps) {
  const normalized = normalizeRuntimeSnapshot(snapshot)
  const backup = normalized.backup
  const freshness = backup.freshness ?? 'unknown'
  const provenance = normalized.provenance ?? {
    state: 'unknown' as const,
    mount_count: 0,
    external_read_only_count: 0,
    source_fingerprint_state: 'unknown' as const,
  }

  return (
    <section
      role="region"
      aria-label="Backup and provenance"
      data-testid="backup-provenance-panel"
      className="grid gap-4 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-lens)] p-4 motion-reduce:transition-none"
    >
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--dn-brass)]">
          Local backup and provenance
        </p>
        <h2 className="mt-1 text-base font-semibold">{FRESHNESS_LABELS[freshness]} backup receipt</h2>
        <p className="mt-1 text-sm text-muted-foreground">{backupMessage(freshness)}</p>
      </header>

      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-semibold">Newest export</dt>
          <dd className="text-muted-foreground">{formatAge(backup.newest_age_seconds ?? null)}</dd>
        </div>
        <div>
          <dt className="font-semibold">Size</dt>
          <dd className="text-muted-foreground">{formatBytes(backup.newest_size_bytes)}</dd>
        </div>
        <div>
          <dt className="font-semibold">Recorded at</dt>
          <dd className="text-muted-foreground">{formatTimestamp(backup.newest_timestamp)}</dd>
        </div>
        <div>
          <dt className="font-semibold">Integrity</dt>
          <dd className="text-muted-foreground">
            {backup.integrity === 'verified' ? 'Integrity verified' : 'Integrity not verified'}
          </dd>
        </div>
        <div>
          <dt className="font-semibold">Export files</dt>
          <dd className="text-muted-foreground">{backup.file_count}</dd>
        </div>
      </dl>

      <div className="border-t border-border/70 pt-3 text-sm">
        <h3 className="font-semibold">External source provenance</h3>
        <p className="mt-1 text-muted-foreground">
          {provenanceMessage(provenance.state, provenance.external_read_only_count)}
        </p>
        <p className="mt-1 text-muted-foreground">
          {provenance.source_fingerprint_state === 'available'
            ? 'Source fingerprints recorded'
            : 'Source fingerprint summary unavailable'}
          . No source content, paths, or hashes are shown.
        </p>
      </div>
    </section>
  )
}
