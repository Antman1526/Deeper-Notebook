import { describe, expect, it } from 'vitest'

import { localModelSettingsSchema, modelRoutePlanSchema, parseRedactedLocalModelResponse } from './local-models'

describe('local-model response parsing', () => {
  it('rejects a nested path leak in a route-plan payload', () => {
    expect(() => parseRedactedLocalModelResponse(modelRoutePlanSchema, {
      role: 'research_chat', outcome: 'ready', selected_model_id: 'local', selected_provider: 'mlx', resource_tier: 'standard',
      selection_source: 'automatic', route_reason: 'verified', escalation_model_ids: [], blocked_reason: null,
      selected_fingerprint: 'fingerprint', selected_measurements: { latency_ms: 3, nested: { path: '/secret/model' } },
    })).toThrow(/path/i)
  })

  it('rejects a nested path leak in settings before schema coercion', () => {
    expect(() => parseRedactedLocalModelResponse(localModelSettingsSchema, {
      model_dir: 'Library', execution_policy: 'strict_local', compute_profile: 'balanced', local_model_memory_limit_bytes: 0,
      role_overrides: { research_chat: 'local', nested: { path: '/secret/override' } }, trusted_external_model_roots: [],
    })).toThrow(/path/i)
  })
})
