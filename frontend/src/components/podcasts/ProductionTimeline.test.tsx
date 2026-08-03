import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProductionTimeline } from './ProductionTimeline'

describe('ProductionTimeline', () => {
  it('supports Arrow/Home/End stage navigation and never completes locked phases', () => {
    const onStageChange = vi.fn()
    render(<ProductionTimeline state="awaiting_outline" selectedStage="Outline Storyboard" onStageChange={onStageChange} />)

    const outline = screen.getByRole('tab', { name: 'Outline Storyboard' })
    outline.focus()
    fireEvent.keyDown(outline, { key: 'ArrowRight' })
    expect(onStageChange).toHaveBeenCalledWith('Script/Voice Job')
    fireEvent.keyDown(outline, { key: 'Home' })
    expect(onStageChange).toHaveBeenCalledWith('Research Set Preview')
    fireEvent.keyDown(outline, { key: 'End' })
    expect(onStageChange).toHaveBeenCalledWith('Episode')

    expect(screen.getByRole('tab', { name: /Evidence/ })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getAllByText('Available after intellectual engine upgrade')).toHaveLength(2)
  })

  it('tracks controller state changes when the tab is not deliberately controlled', () => {
    const { rerender } = render(<ProductionTimeline state="selecting" />)
    expect(screen.getByRole('tab', { name: 'Research Set Preview' })).toHaveAttribute('aria-selected', 'true')

    rerender(<ProductionTimeline state="briefing_ready" />)
    expect(screen.getByRole('tab', { name: 'Editorial Brief' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Research Set Preview' })).toHaveAttribute('data-status', 'complete')
  })
})
