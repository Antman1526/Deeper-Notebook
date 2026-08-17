'use client'

import { RefreshCw } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import {
  normalizeRuntimeSnapshot,
  type RuntimeReasonCode,
  type RuntimeState,
} from '@/lib/api/runtime'

const REASON_LABELS: Record<RuntimeReasonCode, string> = {
  readiness_unknown: 'Core readiness is unavailable',
  database_offline: 'Database is offline',
  database_check_failed: 'Database status is unavailable',
  migrations_pending: 'Migrations are pending',
  migrations_check_failed: 'Migration status is unavailable',
  vault_degraded: 'A local source is degraded',
  vault_unavailable: 'A local source is unavailable',
  vault_unknown: 'Local source status is unavailable',
  knowledge_degraded: 'Knowledge projection is degraded',
  knowledge_unknown: 'Knowledge status is unavailable',
  startup_receipt_unavailable: 'Startup receipt is unavailable',
  startup_receipt_invalid: 'Startup receipt is unreadable',
  updates_disabled: 'Update checks are off',
  updates_unknown: 'Update status is unavailable',
  auto_export_unknown: 'Local backup status is unavailable',
  auto_export_stale: 'Local backup is stale',
  provenance_unknown: 'External source provenance is unavailable',
}

export interface RuntimeStatusPanelProps {
  /** Optional fixture/presentation input; malformed values fail closed. */
  snapshot?: unknown
  isLoading?: boolean
  onRefresh?: () => void
  compact?: boolean
}

function stateLabel(state: RuntimeState): string {
  return state === 'ready' ? 'Ready' : state === 'degraded' ? 'Degraded' : 'Unknown'
}

function readinessLabel(value: string): string {
  return value === 'online' || value === 'applied'
    ? 'Ready'
    : value === 'offline' || value === 'pending'
      ? 'Degraded'
      : 'Unknown'
}

function countLabel(value: number | null): string {
  return value === null ? 'Unknown' : String(value)
}

function RefreshButton({ onRefresh }: { onRefresh: () => void }) {
  return (
    <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
      <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />
      Refresh runtime status
    </Button>
  )
}

export function RuntimeStatusPanel({ snapshot, isLoading, onRefresh, compact = false }: RuntimeStatusPanelProps) {
  const loading = isLoading ?? false
  const normalized = normalizeRuntimeSnapshot(snapshot)
  const refresh = onRefresh ?? (() => {})
  const overallLabel = stateLabel(normalized.status)

  if (loading) {
    return (
      <section
        role="status"
        aria-label="Runtime status loading"
        data-testid="runtime-status-panel"
        className="grid gap-3 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-lens)] p-4 motion-reduce:transition-none"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--dn-brass)]">
              Runtime status
            </p>
            <h2 className="mt-1 text-base font-semibold">Checking local runtime</h2>
          </div>
          <RefreshButton onRefresh={refresh} />
        </div>
        <p className="text-sm text-muted-foreground">Reading a bounded local snapshot. No repair or source action runs.</p>
      </section>
    )
  }

  const role = normalized.status === 'degraded' ? 'alert' : 'status'
  const reasonLabels = normalized.reasons.map((reason) => REASON_LABELS[reason]).filter(Boolean)
  const apiLabel = normalized.status === 'unknown' ? 'Unknown' : 'Ready'

  return (
    <section
      role={role}
      aria-label={`Runtime status ${overallLabel}`}
      data-testid="runtime-status-panel"
      className="grid gap-4 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-lens)] p-4 motion-reduce:transition-none"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--dn-brass)]">
            Runtime status
          </p>
          <h2 className="mt-1 text-base font-semibold">{overallLabel}</h2>
        </div>
        <RefreshButton onRefresh={refresh} />
      </header>

      {reasonLabels.length ? (
        <ul aria-label="Runtime reasons" className="grid gap-1 text-sm text-muted-foreground">
          {reasonLabels.map((label) => <li key={label}>{label}</li>)}
        </ul>
      ) : null}

      <div className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <h3 className="font-semibold">Core services</h3>
          <dl className="mt-2 grid gap-1 text-muted-foreground">
            <div className="flex justify-between gap-3"><dt>API</dt><dd>{apiLabel}</dd></div>
            <div className="flex justify-between gap-3"><dt>Database</dt><dd>{readinessLabel(normalized.readiness.database)}</dd></div>
            <div className="flex justify-between gap-3"><dt>Migrations</dt><dd>{readinessLabel(normalized.readiness.migrations)}</dd></div>
          </dl>
        </div>

        {!compact ? (
          <div>
            <h3 className="font-semibold">Optional capabilities</h3>
            <dl className="mt-2 grid gap-1 text-muted-foreground">
              <div className="flex justify-between gap-3"><dt>Startup receipt</dt><dd>{stateLabel(normalized.startup.state)}</dd></div>
              {/* v0.8.86 — Phase 2B startup measurement: the receipt's stage
                  timings flowed all the way to this payload and stopped here.
                  Show the slow stages (>=100ms) so a degraded launch is
                  diagnosable from the UI instead of the log directory. */}
              {normalized.startup.stages
                .filter((stage) => stage.elapsed_ms >= 100)
                .map((stage) => (
                  <div key={stage.stage} className="flex justify-between gap-3 pl-3">
                    <dt className="truncate">{stage.stage.replaceAll('_', ' ')}</dt>
                    <dd>{stage.elapsed_ms >= 1000
                      ? `${(stage.elapsed_ms / 1000).toFixed(1)}s`
                      : `${stage.elapsed_ms}ms`}</dd>
                  </div>
                ))}
              <div className="flex justify-between gap-3"><dt>Local sources</dt><dd>{stateLabel(normalized.vault.state)}</dd></div>
              <div className="flex justify-between gap-3"><dt>Knowledge</dt><dd>{stateLabel(normalized.knowledge.state)}</dd></div>
              <div className="flex justify-between gap-3"><dt>Backup receipt</dt><dd>{stateLabel(normalized.backup.state)}</dd></div>
            </dl>
          </div>
        ) : null}
      </div>

      {!compact ? (
        <dl className="grid gap-1 border-t border-border/70 pt-3 text-xs text-muted-foreground sm:grid-cols-3">
          <div><dt>Sources ready</dt><dd>{normalized.vault.ready}</dd></div>
          <div><dt>Knowledge projected</dt><dd>{countLabel(normalized.knowledge.projected)}</dd></div>
          <div><dt>Backup files</dt><dd>{normalized.backup.file_count}</dd></div>
        </dl>
      ) : null}
    </section>
  )
}
