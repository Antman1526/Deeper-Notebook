'use client'

import * as React from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'
import { formatDecimal } from '@/lib/utils/format'
import {
  normalizeRuntimeSnapshot,
  type RuntimeBackupFreshness,
} from '@/lib/api/runtime'

export interface BackupProvenancePanelProps {
  /** Optional fixture/presentation input; malformed values fail closed. */
  snapshot?: unknown
}

type TranslateFn = ReturnType<typeof useTranslation>['t']

const FRESHNESS_RECEIPT_KEYS: Record<RuntimeBackupFreshness, string> = {
  valid: 'workspace.backupProvenancePanel.receiptValid',
  stale: 'workspace.backupProvenancePanel.receiptStale',
  unknown: 'workspace.backupProvenancePanel.receiptUnknown',
}

function formatBytes(t: TranslateFn, language: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return t('workspace.backupProvenancePanel.unknownSize')
  if (value < 1024) return t('workspace.backupProvenancePanel.sizeBytes', { value })
  if (value < 1024 * 1024) {
    return t('workspace.backupProvenancePanel.sizeKb', { value: Math.round(value / 1024) })
  }
  if (value < 1024 * 1024 * 1024) {
    return t('workspace.backupProvenancePanel.sizeMb', { value: Math.round(value / (1024 * 1024)) })
  }
  return t('workspace.backupProvenancePanel.sizeGb', {
    value: formatDecimal(value / (1024 * 1024 * 1024), language, 1),
  })
}

function formatAge(t: TranslateFn, value: number | null): string {
  if (value === null) return t('workspace.backupProvenancePanel.unknownAge')
  if (value < 60) return t('workspace.backupProvenancePanel.ageSeconds', { count: value })
  if (value < 3600) {
    return t('workspace.backupProvenancePanel.ageMinutes', { count: Math.floor(value / 60) })
  }
  if (value < 86_400) {
    return t('workspace.backupProvenancePanel.ageHours', { count: Math.floor(value / 3600) })
  }
  return t('workspace.backupProvenancePanel.ageDays', { count: Math.floor(value / 86_400) })
}

function formatTimestamp(t: TranslateFn, value: string | null | undefined): string {
  if (!value) return t('workspace.backupProvenancePanel.unknownTimestamp')
  try {
    return new Date(value).toISOString()
  } catch {
    return t('workspace.backupProvenancePanel.unknownTimestamp')
  }
}

function backupMessage(t: TranslateFn, freshness: RuntimeBackupFreshness): string {
  if (freshness === 'valid') return t('workspace.backupProvenancePanel.messageValid')
  if (freshness === 'stale') return t('workspace.backupProvenancePanel.messageStale')
  return t('workspace.backupProvenancePanel.messageUnknown')
}

function provenanceMessage(t: TranslateFn, state: string, count: number): string {
  if (state === 'unknown') return t('workspace.backupProvenancePanel.provenanceUnavailable')
  return count === 1
    ? t('workspace.backupProvenancePanel.externalSpaceOne', { count })
    : t('workspace.backupProvenancePanel.externalSpaceOther', { count })
}

export function BackupProvenancePanel({ snapshot }: BackupProvenancePanelProps) {
  const { t, language } = useTranslation()
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
      aria-label={t('workspace.backupProvenancePanel.ariaLabel')}
      data-testid="backup-provenance-panel"
      className="grid gap-4 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-lens)] p-4 motion-reduce:transition-none"
    >
      <header>
        <p className="text-xs font-semibold text-[var(--dn-brass)]">
          {t('workspace.backupProvenancePanel.eyebrow')}
        </p>
        <h2 className="mt-1 text-base font-semibold">{t(FRESHNESS_RECEIPT_KEYS[freshness])}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{backupMessage(t, freshness)}</p>
      </header>

      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-semibold">{t('workspace.backupProvenancePanel.newestExport')}</dt>
          <dd className="text-muted-foreground">{formatAge(t, backup.newest_age_seconds ?? null)}</dd>
        </div>
        <div>
          <dt className="font-semibold">{t('workspace.backupProvenancePanel.size')}</dt>
          <dd className="text-muted-foreground">{formatBytes(t, language, backup.newest_size_bytes)}</dd>
        </div>
        <div>
          <dt className="font-semibold">{t('workspace.backupProvenancePanel.recordedAt')}</dt>
          <dd className="text-muted-foreground">{formatTimestamp(t, backup.newest_timestamp)}</dd>
        </div>
        <div>
          <dt className="font-semibold">{t('workspace.backupProvenancePanel.integrity')}</dt>
          <dd className="text-muted-foreground">
            {backup.integrity === 'verified'
              ? t('workspace.backupProvenancePanel.integrityVerified')
              : t('workspace.backupProvenancePanel.integrityNotVerified')}
          </dd>
        </div>
        <div>
          <dt className="font-semibold">{t('workspace.backupProvenancePanel.exportFiles')}</dt>
          <dd className="text-muted-foreground">{backup.file_count}</dd>
        </div>
      </dl>

      <div className="border-t border-border/70 pt-3 text-sm">
        <h3 className="font-semibold">{t('workspace.backupProvenancePanel.externalSourceProvenance')}</h3>
        <p className="mt-1 text-muted-foreground">
          {provenanceMessage(t, provenance.state, provenance.external_read_only_count)}
        </p>
        <p className="mt-1 text-muted-foreground">
          {provenance.source_fingerprint_state === 'available'
            ? t('workspace.backupProvenancePanel.fingerprintsRecorded')
            : t('workspace.backupProvenancePanel.fingerprintsUnavailable')}
        </p>
      </div>
    </section>
  )
}
