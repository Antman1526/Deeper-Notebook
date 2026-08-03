import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PodcastModelPlan } from './PodcastModelPlan'

describe('PodcastModelPlan', () => {
  it('distinguishes ready, blocked, approval-required routes and reports safe details', () => {
    const onOverride = vi.fn()
    render(<PodcastModelPlan
      plans={[
        { stage: 'outline', label: 'Outline', role: 'podcast_outline', outcome: 'ready', modelId: 'local-outline', provider: 'mlx', resourceTier: 'light', selectionSource: 'automatic', reason: 'Verified local route.' },
        { stage: 'script', label: 'Script', role: 'podcast_script', outcome: 'blocked', modelId: null, provider: null, resourceTier: null, selectionSource: null, reason: 'No eligible route.' },
        { stage: 'voice', label: 'Voice', role: 'text_to_speech', outcome: 'approval_required', modelId: 'voice-model', provider: 'mlx', resourceTier: 'standard', selectionSource: 'production_override', reason: 'Owner approval required.' },
      ]}
      overrideChoices={{ outline: ['local-outline', 'other-local'] }}
      onOverride={onOverride}
    />)

    expect(screen.getByText('Verified local route.')).toBeVisible()
    expect(screen.getByText('Blocked')).toBeVisible()
    expect(screen.getByText('Approval required')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Override Outline model'), { target: { value: 'other-local' } })
    expect(onOverride).toHaveBeenCalledWith('outline', 'other-local')
  })

  it('preserves prose and HTTPS explanations while redacting embedded absolute paths', () => {
    render(<PodcastModelPlan plans={[
      {
        stage: 'outline', label: 'Outline', role: 'podcast_outline', outcome: 'ready',
        modelId: 'manifest:org/model', provider: 'mlx', resourceTier: 'light', selectionSource: 'automatic',
        reason: 'Compare pros/cons and/or 1/2 at https://example.com/Users/owner/guide; source /Volumes/Private/plan.md.',
      },
    ]} />)

    expect(screen.getByText('Compare pros/cons and/or 1/2 at https://example.com/Users/owner/guide; source [path redacted]')).toBeVisible()
    expect(screen.getByText(/manifest:org\/model/)).toBeVisible()
  })
})
