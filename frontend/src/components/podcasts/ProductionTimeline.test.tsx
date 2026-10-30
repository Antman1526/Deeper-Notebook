import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProductionTimeline } from './ProductionTimeline'

// Echo interpolation values so the locked Evidence stage stays addressable by name.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key} ${JSON.stringify(options)}` : key),
  }),
}))

describe('ProductionTimeline', () => {
  it('supports Arrow/Home/End stage navigation and never completes locked phases', () => {
    const onStageChange = vi.fn()
    render(<ProductionTimeline state="awaiting_outline" selectedStage="Outline Storyboard" onStageChange={onStageChange} />)

    const outline = screen.getByRole('tab', { name: 'podcasts.productionTimeline.stageOutlineStoryboard' })
    outline.focus()
    fireEvent.keyDown(outline, { key: 'ArrowRight' })
    expect(onStageChange).toHaveBeenCalledWith('Script/Voice Job')
    fireEvent.keyDown(outline, { key: 'Home' })
    expect(onStageChange).toHaveBeenCalledWith('Research Set Preview')
    fireEvent.keyDown(outline, { key: 'End' })
    expect(onStageChange).toHaveBeenCalledWith('Episode')

    expect(screen.getByRole('tab', { name: 'podcasts.productionTimeline.lockedLabel {"stage":"podcasts.productionTimeline.stageEvidence"}' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getAllByText('podcasts.productionTimeline.lockedDetail')).toHaveLength(2)
  })

  it('tracks controller state changes when the tab is not deliberately controlled', () => {
    const { rerender } = render(<ProductionTimeline state="selecting" />)
    expect(screen.getByRole('tab', { name: 'podcasts.productionTimeline.stageResearchSetPreview' })).toHaveAttribute('aria-selected', 'true')

    rerender(<ProductionTimeline state="briefing_ready" />)
    expect(screen.getByRole('tab', { name: 'podcasts.productionTimeline.stageEditorialBrief' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'podcasts.productionTimeline.stageResearchSetPreview' })).toHaveAttribute('data-status', 'complete')
  })
})
