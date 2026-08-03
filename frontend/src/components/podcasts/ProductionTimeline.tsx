'use client'

import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

export type PodcastStudioState = 'selecting' | 'preview_ready' | 'briefing_ready' | 'submitted' | 'awaiting_outline' | 'generating' | 'completed' | 'failed' | 'cancelled'
export type ProductionStageName = 'Research Set Preview' | 'Editorial Brief' | 'Outline Storyboard' | 'Script/Voice Job' | 'Episode'

export const PRODUCTION_STAGES: Array<{ name: ProductionStageName; detail: string }> = [
  { name: 'Research Set Preview', detail: 'Resolve stable references and review inclusion.' },
  { name: 'Editorial Brief', detail: 'Set audience, purpose, format, and takeaway.' },
  { name: 'Outline Storyboard', detail: 'Review the current production outline gate.' },
  { name: 'Script/Voice Job', detail: 'Starts only after outline approval.' },
  { name: 'Episode', detail: 'Play and review current production output.' },
]

export interface ProductionTimelineProps {
  state: PodcastStudioState
  selectedStage?: ProductionStageName
  onStageChange?: (stage: ProductionStageName) => void
  children?: ReactNode
}

const stageIndexForState: Record<PodcastStudioState, number> = {
  selecting: 0, preview_ready: 0, briefing_ready: 1, submitted: 2, awaiting_outline: 2,
  generating: 3, completed: 4, failed: 3, cancelled: 0,
}

function stageStatus(index: number, state: PodcastStudioState): 'complete' | 'current' | 'upcoming' {
  const current = stageIndexForState[state]
  if (state === 'selecting' || state === 'cancelled') return index === current ? 'current' : 'upcoming'
  if (index < current) return 'complete'
  return index === current ? 'current' : 'upcoming'
}

export function ProductionTimeline({ state, selectedStage, onStageChange, children }: ProductionTimelineProps) {
  const [internalStage, setInternalStage] = useState<ProductionStageName>(selectedStage ?? PRODUCTION_STAGES[stageIndexForState[state]].name)
  const stageRefs = useRef<Record<number, HTMLButtonElement | null>>({})
  const activeStage = selectedStage ?? internalStage
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
    <section data-studio-region="production-timeline" data-region="production-timeline" aria-label="Production Timeline" className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">Production Timeline</h3>
        <p className="mt-1 text-sm text-muted-foreground">Current controller state: {state.replaceAll('_', ' ')}</p>
      </header>
      <div role="tablist" aria-label="Production stages" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {PRODUCTION_STAGES.map((stage, index) => {
          const status = stageStatus(index, state)
          return (
            <button ref={(element) => { stageRefs.current[index] = element }} key={stage.name} type="button" role="tab" aria-label={stage.name} aria-selected={activeStage === stage.name} data-status={status} className="rounded border p-2 text-left text-sm" onClick={() => move(index)} onKeyDown={(event) => handleKeyDown(event, index)}>
              <span className="block font-medium">{stage.name}</span><span className="mt-1 block text-xs text-muted-foreground">{stage.detail}</span><span className="mt-1 block text-xs uppercase tracking-wide text-muted-foreground">{status}</span>
            </button>
          )
        })}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {(['Evidence', 'Verification'] as const).map((stage) => (
          <div key={stage} role="tab" aria-disabled="true" aria-label={`${stage} — locked`} data-status="locked" className="rounded border border-dashed p-3 text-sm">
            <span className="font-medium">{stage}</span><span className="mt-1 block text-xs text-muted-foreground">Available after intellectual engine upgrade</span>
          </div>
        ))}
      </div>
      {children}
    </section>
  )
}
