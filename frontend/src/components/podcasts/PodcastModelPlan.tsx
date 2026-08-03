'use client'

import type { PodcastStageModelPlan } from '@/lib/types/podcasts'

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
}

export interface PodcastModelPlanProps {
  plans: PodcastModelPlanItem[]
  overrideChoices?: Partial<Record<PodcastModelPlanItem['stage'], string[]>>
  onOverride?: (stage: PodcastModelPlanItem['stage'], modelId: string) => void
}

const OUTCOME_LABELS: Record<PodcastStageModelPlan['outcome'], string> = {
  ready: 'Ready', blocked: 'Blocked', approval_required: 'Approval required',
}

function safeDetail(value: string): string {
  if (/^(?:[\\/]|[A-Za-z]:[\\/])/.test(value)) return value.split(/[\\/]/).pop() || '[local model]'
  return value
    .replace(/file:\/\/[^\s,;)]*/gi, '[path redacted]')
    .replace(/[A-Za-z]:[\\/][^\s,;)]*/g, '[path redacted]')
    .replace(/\\\\[^\s,;)]*/g, '[path redacted]')
    .replace(/(?<!:)\/(?:[^/\s,;]+[\\/])*[^/\s,;]+/g, '[path redacted]')
}

export function PodcastModelPlan({ plans, overrideChoices = {}, onOverride }: PodcastModelPlanProps) {
  return (
    <section data-region="model-plan" aria-label="Podcast Model Plan" className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">Model Plan</h3>
        <p className="mt-1 text-sm text-muted-foreground">Route details are inspectable; choosing an override never loads a model on mount.</p>
      </header>
      {plans.length === 0 ? <p className="text-sm text-muted-foreground">No route plans available yet.</p> : null}
      <ul className="grid gap-3 sm:grid-cols-2">
        {plans.map((plan) => (
          <li key={`${plan.stage}:${plan.role}`} className="rounded border p-3 text-sm" data-outcome={plan.outcome}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{plan.label}</span>
              <span className={plan.outcome === 'blocked' ? 'text-destructive' : plan.outcome === 'approval_required' ? 'text-amber-700' : 'text-muted-foreground'}>{OUTCOME_LABELS[plan.outcome]}</span>
            </div>
            <p className="mt-1 text-muted-foreground">{safeDetail(plan.reason)}</p>
            {plan.modelId || plan.provider || plan.resourceTier ? <p className="mt-1 text-xs text-muted-foreground">{[plan.modelId, plan.provider, plan.resourceTier].filter(Boolean).map((detail) => safeDetail(String(detail))).join(' · ')}</p> : null}
            {overrideChoices[plan.stage]?.length && onOverride ? (
              <label className="mt-2 grid gap-1 text-xs" htmlFor={`podcast-model-override-${plan.stage}`}>Override {plan.label} model
                <select id={`podcast-model-override-${plan.stage}`} value={plan.modelId ?? ''} onChange={(event) => onOverride(plan.stage, event.target.value)} className="h-8 rounded border bg-background px-2 text-sm">
                  <option value="">Automatic route</option>{overrideChoices[plan.stage]!.map((modelId) => <option key={modelId} value={modelId}>{modelId}</option>)}
                </select>
              </label>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
