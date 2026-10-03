'use client'

import { RefreshCw } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { RUNTIME_STARTUP_STAGE_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  normalizeRuntimeSnapshot,
  type RuntimeReasonCode,
  type RuntimeState,
} from '@/lib/api/runtime'

const REASON_LABEL_KEYS: Record<RuntimeReasonCode, string> = {
  readiness_unknown: 'workspace.runtimeStatusPanel.reasons.readinessUnknown',
  database_offline: 'workspace.runtimeStatusPanel.reasons.databaseOffline',
  database_check_failed: 'workspace.runtimeStatusPanel.reasons.databaseCheckFailed',
  migrations_pending: 'workspace.runtimeStatusPanel.reasons.migrationsPending',
  migrations_check_failed: 'workspace.runtimeStatusPanel.reasons.migrationsCheckFailed',
  vault_degraded: 'workspace.runtimeStatusPanel.reasons.vaultDegraded',
  vault_unavailable: 'workspace.runtimeStatusPanel.reasons.vaultUnavailable',
  vault_unknown: 'workspace.runtimeStatusPanel.reasons.vaultUnknown',
  knowledge_degraded: 'workspace.runtimeStatusPanel.reasons.knowledgeDegraded',
  knowledge_unknown: 'workspace.runtimeStatusPanel.reasons.knowledgeUnknown',
  startup_receipt_unavailable: 'workspace.runtimeStatusPanel.reasons.startupReceiptUnavailable',
  startup_receipt_invalid: 'workspace.runtimeStatusPanel.reasons.startupReceiptInvalid',
  updates_disabled: 'workspace.runtimeStatusPanel.reasons.updatesDisabled',
  updates_unknown: 'workspace.runtimeStatusPanel.reasons.updatesUnknown',
  auto_export_unknown: 'workspace.runtimeStatusPanel.reasons.autoExportUnknown',
  auto_export_stale: 'workspace.runtimeStatusPanel.reasons.autoExportStale',
  provenance_unknown: 'workspace.runtimeStatusPanel.reasons.provenanceUnknown',
  model_config_degraded: 'workspace.runtimeStatusPanel.reasons.modelConfigDegraded',
  model_config_unknown: 'workspace.runtimeStatusPanel.reasons.modelConfigUnknown',
}

export interface RuntimeStatusPanelProps {
  /** Optional fixture/presentation input; malformed values fail closed. */
  snapshot?: unknown
  isLoading?: boolean
  onRefresh?: () => void
  compact?: boolean
}

type TranslateFn = ReturnType<typeof useTranslation>['t']

const STATE_ARIA_LABEL_KEYS: Record<RuntimeState, string> = {
  ready: 'workspace.runtimeStatusPanel.ariaLabelReady',
  degraded: 'workspace.runtimeStatusPanel.ariaLabelDegraded',
  unknown: 'workspace.runtimeStatusPanel.ariaLabelUnknown',
}

function stateLabel(t: TranslateFn, state: RuntimeState): string {
  return state === 'ready'
    ? t('workspace.runtimeStatusPanel.stateReady')
    : state === 'degraded'
      ? t('workspace.runtimeStatusPanel.stateDegraded')
      : t('workspace.runtimeStatusPanel.stateUnknown')
}

function readinessLabel(t: TranslateFn, value: string): string {
  return value === 'online' || value === 'applied'
    ? t('workspace.runtimeStatusPanel.stateReady')
    : value === 'offline' || value === 'pending'
      ? t('workspace.runtimeStatusPanel.stateDegraded')
      : t('workspace.runtimeStatusPanel.stateUnknown')
}

function countLabel(t: TranslateFn, value: number | null): string {
  return value === null ? t('workspace.runtimeStatusPanel.stateUnknown') : String(value)
}

function RefreshButton({ onRefresh }: { onRefresh: () => void }) {
  const { t } = useTranslation()
  return (
    <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
      <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />
      {t('workspace.runtimeStatusPanel.refresh')}
    </Button>
  )
}

export function RuntimeStatusPanel({ snapshot, isLoading, onRefresh, compact = false }: RuntimeStatusPanelProps) {
  const { t } = useTranslation()
  const loading = isLoading ?? false
  const normalized = normalizeRuntimeSnapshot(snapshot)
  const refresh = onRefresh ?? (() => {})
  const overallLabel = stateLabel(t, normalized.status)

  if (loading) {
    return (
      <section
        role="status"
        aria-label={t('workspace.runtimeStatusPanel.loadingAriaLabel')}
        data-testid="runtime-status-panel"
        data-dn-runtime-status=""
        className="grid gap-3 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-lens)] p-4 motion-reduce:transition-none"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              {t('workspace.runtimeStatusPanel.title')}
            </p>
            <h2 className="mt-1 text-base font-semibold">{t('workspace.runtimeStatusPanel.checking')}</h2>
          </div>
          <RefreshButton onRefresh={refresh} />
        </div>
        <p className="text-sm text-muted-foreground">{t('workspace.runtimeStatusPanel.checkingDescription')}</p>
      </section>
    )
  }

  const role = normalized.status === 'degraded' ? 'alert' : 'status'
  const reasonLabels = normalized.reasons
    .map((reason) => (REASON_LABEL_KEYS[reason] ? t(REASON_LABEL_KEYS[reason]) : undefined))
    .filter(Boolean)
  const modelConfigIssues = normalized.model_config_health?.issues ?? []
  const apiLabel = normalized.status === 'unknown'
    ? t('workspace.runtimeStatusPanel.stateUnknown')
    : t('workspace.runtimeStatusPanel.stateReady')

  return (
    <section
      role={role}
      aria-label={t(STATE_ARIA_LABEL_KEYS[normalized.status])}
      data-testid="runtime-status-panel"
      data-dn-runtime-status=""
      className="grid gap-4 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-lens)] p-4 motion-reduce:transition-none"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">
            {t('workspace.runtimeStatusPanel.title')}
          </p>
          <h2 className="mt-1 text-base font-semibold">{overallLabel}</h2>
        </div>
        <RefreshButton onRefresh={refresh} />
      </header>

      {reasonLabels.length ? (
        <ul aria-label={t('workspace.runtimeStatusPanel.reasonsAriaLabel')} className="grid gap-1 text-sm text-muted-foreground">
          {reasonLabels.map((label) => <li key={label}>{label}</li>)}
        </ul>
      ) : null}

      {/* v0.8.104 — the reason code alone ("Model configuration needs
          attention") is the same unhelpful shape as the log nobody opens.
          What makes this actionable is the detail (which setting, which id)
          and the remedy (where to go), so both are rendered verbatim. */}
      {modelConfigIssues.length ? (
        <ul
          aria-label={t('workspace.runtimeStatusPanel.modelConfigIssuesAriaLabel')}
          data-testid="runtime-model-config-issues"
          className="grid gap-2 rounded-lg border border-[var(--dn-paper-edge)] p-3 text-sm"
        >
          {modelConfigIssues.map((issue) => (
            <li key={issue.code} className="grid gap-0.5">
              <span className="font-medium">{issue.detail}</span>
              <span className="text-muted-foreground">{issue.remedy}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <h3 className="font-semibold">{t('workspace.runtimeStatusPanel.coreServices')}</h3>
          <dl className="mt-2 grid gap-1 text-muted-foreground">
            <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.api')}</dt><dd>{apiLabel}</dd></div>
            <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.database')}</dt><dd>{readinessLabel(t, normalized.readiness.database)}</dd></div>
            <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.migrations')}</dt><dd>{readinessLabel(t, normalized.readiness.migrations)}</dd></div>
          </dl>
        </div>

        {!compact ? (
          <div>
            <h3 className="font-semibold">{t('workspace.runtimeStatusPanel.optionalCapabilities')}</h3>
            <dl className="mt-2 grid gap-1 text-muted-foreground">
              <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.startupReceipt')}</dt><dd>{stateLabel(t, normalized.startup.state)}</dd></div>
              {/* v0.8.86 — Phase 2B startup measurement: the receipt's stage
                  timings flowed all the way to this payload and stopped here.
                  Show the slow stages (>=100ms) so a degraded launch is
                  diagnosable from the UI instead of the log directory. */}
              {normalized.startup.stages
                .filter((stage) => stage.elapsed_ms >= 100)
                .map((stage) => (
                  <div key={stage.stage} className="flex justify-between gap-3 pl-3">
                    <dt className="truncate">{enumLabel(t, RUNTIME_STARTUP_STAGE_KEYS, stage.stage, spacedEnum(stage.stage))}</dt>
                    <dd>{stage.elapsed_ms >= 1000
                      ? t('workspace.runtimeStatusPanel.stageSeconds', { value: (stage.elapsed_ms / 1000).toFixed(1) })
                      : t('workspace.runtimeStatusPanel.stageMilliseconds', { value: stage.elapsed_ms })}</dd>
                  </div>
                ))}
              <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.localSources')}</dt><dd>{stateLabel(t, normalized.vault.state)}</dd></div>
              <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.knowledge')}</dt><dd>{stateLabel(t, normalized.knowledge.state)}</dd></div>
              <div className="flex justify-between gap-3"><dt>{t('workspace.runtimeStatusPanel.backupReceipt')}</dt><dd>{stateLabel(t, normalized.backup.state)}</dd></div>
            </dl>
          </div>
        ) : null}
      </div>

      {!compact ? (
        <dl className="grid gap-1 border-t border-border/70 pt-3 text-xs text-muted-foreground sm:grid-cols-3">
          <div><dt>{t('workspace.runtimeStatusPanel.sourcesReady')}</dt><dd>{normalized.vault.ready}</dd></div>
          <div><dt>{t('workspace.runtimeStatusPanel.knowledgeProjected')}</dt><dd>{countLabel(t, normalized.knowledge.projected)}</dd></div>
          <div><dt>{t('workspace.runtimeStatusPanel.backupFiles')}</dt><dd>{normalized.backup.file_count}</dd></div>
        </dl>
      ) : null}
    </section>
  )
}
