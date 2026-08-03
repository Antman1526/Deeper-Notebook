import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ModelRoutePlanPanel } from './ModelRoutePlanPanel'

describe('ModelRoutePlanPanel', () => {
  it('explains a blocked explicit override without exposing paths', () => {
    render(<ModelRoutePlanPanel
      title="Research Chat route"
      plan={{
        role: 'research_chat', outcome: 'blocked', selected_model_id: null,
        selected_provider: null, resource_tier: null, selection_source: 'role_override',
        route_reason: 'The requested override failed the readiness gate.',
        escalation_model_ids: [], blocked_reason: 'Override model is not ready_verified.',
        selected_fingerprint: null, selected_measurements: {},
      }}
    />)

    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText(/Override model is not ready_verified/)).toBeInTheDocument()
    expect(screen.queryByText(/\/[Uu]sers\//)).not.toBeInTheDocument()
  })

  it('labels a degraded route without treating it as ready', () => {
    render(<ModelRoutePlanPanel
      title="Embedding route"
      plan={{
        role: 'embedding_retrieval', outcome: 'approval_required', selected_model_id: null,
        selected_provider: null, resource_tier: null, selection_source: null,
        route_reason: 'A cloud route requires contextual approval.', escalation_model_ids: [],
        blocked_reason: null, selected_fingerprint: null, selected_measurements: {},
      }}
    />)

    expect(screen.getByText('Approval required')).toBeInTheDocument()
    expect(screen.getByText(/requires contextual approval/)).toBeInTheDocument()
  })
})
