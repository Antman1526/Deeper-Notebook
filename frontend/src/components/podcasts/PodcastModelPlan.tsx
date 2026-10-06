'use client'

import { useTranslation } from '@/lib/hooks/use-translation'
import type { PodcastStageModelPlan } from '@/lib/types/podcasts'
import { isAbsoluteFilesystemPath, redactAbsolutePaths } from '@/lib/podcasts/safe-text'

export interface PodcastModelPlanItem {
  stage: 'outline' | 'script' | 'voice' | 'transcription' | 'evidence' | 'verification'
  label: string
  role: PodcastStageModelPlan['role'] | 'evidence_extraction' | 'claim_verification'
  outcome: PodcastStageModelPlan['outcome']
  reason: string
  modelId?: string | null
  provider?: string | null
  resourceTier?: PodcastStageModelPlan['resourceTier']
  selectionSource?: PodcastStageModelPlan['selectionSource']
  overrideChoices?: string[]
  pendingOverride?: boolean
}

export interface PodcastModelPlanProps {
  plans: PodcastModelPlanItem[]
  overrideChoices?: Partial<Record<PodcastModelPlanItem['stage'], string[]>>
  onOverride?: (stage: PodcastModelPlanItem['stage'], modelId: string) => void
}

const OUTCOME_LABEL_KEYS: Record<PodcastStageModelPlan['outcome'], string> = {
  ready: 'podcasts.podcastModelPlan.outcomeReady', blocked: 'podcasts.podcastModelPlan.outcomeBlocked', approval_required: 'podcasts.podcastModelPlan.outcomeApprovalRequired',
}

function safeDetail(value: string, localModelLabel: string): string {
  if (isAbsoluteFilesystemPath(value)) return value.split(/[\\/]/).filter(Boolean).pop() || localModelLabel
  return redactAbsolutePaths(value)
}

export function PodcastModelPlan({ plans, overrideChoices = {}, onOverride }: PodcastModelPlanProps) {
  const { t } = useTranslation()
  const localModelLabel = t('podcasts.podcastModelPlan.localModel')
  return (
    <section data-region="model-plan" aria-label={t('podcasts.podcastModelPlan.title')} className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">{t('podcasts.podcastModelPlan.heading')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('podcasts.podcastModelPlan.description')}</p>
      </header>
      {plans.length === 0 ? <p className="text-sm text-muted-foreground">{t('podcasts.podcastModelPlan.noPlans')}</p> : null}
      <ul className="grid gap-3 sm:grid-cols-2">
        {plans.map((plan) => (
          <li key={`${plan.stage}:${plan.role}`} className="rounded border p-3 text-sm" data-outcome={plan.outcome}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{plan.label}</span>
              {/* v0.8.130 — status colours from theme tokens (UI audit Phase 1) */}
              <span className={plan.outcome === 'blocked' ? 'text-destructive' : plan.outcome === 'approval_required' ? 'text-warning-ink' : 'text-muted-foreground'}>{t(OUTCOME_LABEL_KEYS[plan.outcome])}</span>
            </div>
            <p className="mt-1 text-muted-foreground">{safeDetail(plan.reason, localModelLabel)}</p>
            {plan.modelId || plan.provider || plan.resourceTier ? <p className="mt-1 text-xs text-muted-foreground">{[plan.modelId, plan.provider, plan.resourceTier].filter(Boolean).map((detail) => safeDetail(String(detail), localModelLabel)).join(' · ')}</p> : null}
            {plan.pendingOverride ? <p className="mt-1 text-xs text-muted-foreground">{t('podcasts.podcastModelPlan.overridePending')}</p> : plan.selectionSource ? <p className="mt-1 text-xs text-muted-foreground">{t('podcasts.podcastModelPlan.selectionSource', { source: plan.selectionSource })}</p> : null}
            {overrideChoices[plan.stage]?.length && onOverride ? (
              <label className="mt-2 grid gap-1 text-xs" htmlFor={`podcast-model-override-${plan.stage}`}>{t('podcasts.podcastModelPlan.overrideModel', { label: plan.label })}
                <select id={`podcast-model-override-${plan.stage}`} value={plan.modelId ?? ''} onChange={(event) => onOverride(plan.stage, event.target.value)} className="h-8 rounded border bg-background px-2 text-sm">
                  <option value="">{t('podcasts.podcastModelPlan.automaticRoute')}</option>{overrideChoices[plan.stage]!.map((modelId) => <option key={modelId} value={modelId}>{modelId}</option>)}
                </select>
              </label>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
