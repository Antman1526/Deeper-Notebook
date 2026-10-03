'use client'

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

export type PodcastStudioState = 'selecting' | 'preview_ready' | 'briefing_ready' | 'submitted' | 'awaiting_outline' | 'generating' | 'completed' | 'failed' | 'cancelled'
export type ProductionStageName = 'Research Set Preview' | 'Editorial Brief' | 'Outline Storyboard' | 'Script/Voice Job' | 'Episode'

/** `name` is a stable identifier; `nameKey` / `detailKey` are i18n keys for display. */
export const PRODUCTION_STAGES: Array<{ name: ProductionStageName; nameKey: string; detailKey: string }> = [
  { name: 'Research Set Preview', nameKey: 'podcasts.productionTimeline.stageResearchSetPreview', detailKey: 'podcasts.productionTimeline.stageResearchSetPreviewDetail' },
  { name: 'Editorial Brief', nameKey: 'podcasts.productionTimeline.stageEditorialBrief', detailKey: 'podcasts.productionTimeline.stageEditorialBriefDetail' },
  { name: 'Outline Storyboard', nameKey: 'podcasts.productionTimeline.stageOutlineStoryboard', detailKey: 'podcasts.productionTimeline.stageOutlineStoryboardDetail' },
  { name: 'Script/Voice Job', nameKey: 'podcasts.productionTimeline.stageScriptVoiceJob', detailKey: 'podcasts.productionTimeline.stageScriptVoiceJobDetail' },
  { name: 'Episode', nameKey: 'podcasts.productionTimeline.stageEpisode', detailKey: 'podcasts.productionTimeline.stageEpisodeDetail' },
]

const STATE_LABEL_KEYS: Record<PodcastStudioState, string> = {
  selecting: 'podcasts.productionTimeline.stateSelecting',
  preview_ready: 'podcasts.productionTimeline.statePreviewReady',
  briefing_ready: 'podcasts.productionTimeline.stateBriefingReady',
  submitted: 'podcasts.productionTimeline.stateSubmitted',
  awaiting_outline: 'podcasts.productionTimeline.stateAwaitingOutline',
  generating: 'podcasts.productionTimeline.stateGenerating',
  completed: 'podcasts.productionTimeline.stateCompleted',
  failed: 'podcasts.productionTimeline.stateFailed',
  cancelled: 'podcasts.productionTimeline.stateCancelled',
}

const STATUS_LABEL_KEYS = {
  complete: 'podcasts.productionTimeline.statusComplete',
  current: 'podcasts.productionTimeline.statusCurrent',
  upcoming: 'podcasts.productionTimeline.statusUpcoming',
} as const

const LOCKED_STAGES = [
  { id: 'Evidence', nameKey: 'podcasts.productionTimeline.stageEvidence' },
  { id: 'Verification', nameKey: 'podcasts.productionTimeline.stageVerification' },
] as const

export interface ProductionTimelineProps {
  state: PodcastStudioState
  selectedStage?: ProductionStageName
  onStageChange?: (stage: ProductionStageName) => void
  children?: ReactNode
}

const stageIndexForState: Record<PodcastStudioState, number> = {
  selecting: 0, preview_ready: 0, briefing_ready: 1, submitted: 2, awaiting_outline: 2,
  generating: 3, completed: 4, failed: 2, cancelled: 0,
}

function stageStatus(index: number, state: PodcastStudioState): 'complete' | 'current' | 'upcoming' {
  const current = stageIndexForState[state]
  if (state === 'selecting' || state === 'cancelled') return index === current ? 'current' : 'upcoming'
  if (index < current) return 'complete'
  return index === current ? 'current' : 'upcoming'
}

export function ProductionTimeline({ state, selectedStage, onStageChange, children }: ProductionTimelineProps) {
  const { t } = useTranslation()
  const [internalStage, setInternalStage] = useState<ProductionStageName>(selectedStage ?? PRODUCTION_STAGES[stageIndexForState[state]].name)
  const stageRefs = useRef<Record<number, HTMLButtonElement | null>>({})
  const activeStage = selectedStage ?? internalStage
  useEffect(() => {
    if (selectedStage === undefined) {
      setInternalStage(PRODUCTION_STAGES[stageIndexForState[state]].name)
    }
  }, [selectedStage, state])
  const move = (index: number) => {
    if (index < 0 || index >= PRODUCTION_STAGES.length) return
    const next = PRODUCTION_STAGES[index].name
    setInternalStage(next)
    onStageChange?.(next)
    stageRefs.current[index]?.focus()
  }
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'ArrowRight') { event.preventDefault(); move(index + 1) }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); move(index - 1) }
    else if (event.key === 'Home') { event.preventDefault(); move(0) }
    else if (event.key === 'End') { event.preventDefault(); move(PRODUCTION_STAGES.length - 1) }
  }

  return (
    <section data-studio-region="production-timeline" data-region="production-timeline" aria-label={t('podcasts.productionTimeline.title')} className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">{t('podcasts.productionTimeline.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('podcasts.productionTimeline.controllerState', { state: t(STATE_LABEL_KEYS[state]) })}</p>
      </header>
      <div role="tablist" aria-label={t('podcasts.productionTimeline.stages')} className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {PRODUCTION_STAGES.map((stage, index) => {
          const status = stageStatus(index, state)
          return (
            <button ref={(element) => { stageRefs.current[index] = element }} key={stage.name} type="button" role="tab" aria-label={t(stage.nameKey)} aria-selected={activeStage === stage.name} data-status={status} className="rounded border p-2 text-left text-sm" onClick={() => move(index)} onKeyDown={(event) => handleKeyDown(event, index)}>
              <span className="block font-medium">{t(stage.nameKey)}</span><span className="mt-1 block text-xs text-muted-foreground">{t(stage.detailKey)}</span><span className="mt-1 block text-xs uppercase tracking-wide text-muted-foreground">{t(STATUS_LABEL_KEYS[status])}</span>
            </button>
          )
        })}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {LOCKED_STAGES.map((stage) => (
          <div key={stage.id} role="tab" aria-disabled="true" aria-label={t('podcasts.productionTimeline.lockedLabel', { stage: t(stage.nameKey) })} data-status="locked" className="rounded border border-dashed p-3 text-sm">
            <span className="font-medium">{t(stage.nameKey)}</span><span className="mt-1 block text-xs text-muted-foreground">{t('podcasts.productionTimeline.lockedDetail')}</span>
          </div>
        ))}
      </div>
      {children}
    </section>
  )
}
