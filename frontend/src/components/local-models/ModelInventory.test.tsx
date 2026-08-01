import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { ModelInventory } from './ModelInventory'

describe('ModelInventory', () => {
  it('renders API-provided inventory metadata without resolving a local path in the browser', () => {
    render(
      <ModelInventory
        inventory={{ model_dir: '/Users/Antman/Desktop/AI_Models', available: true, models: [{
          name: 'Qwen local', path: '/resolved/by-api/Qwen.gguf', runtime: 'gguf',
          runnable: true, architecture: 'qwen2', context_length: 32768,
          quant: 'Q4_K_M', parameter_count_b: 7, file_size_bytes: 4_000_000_000,
        }] }}
        health={[]}
        onRefresh={vi.fn()}
      />,
    )

    expect(screen.getByText('Qwen local')).toBeInTheDocument()
    expect(screen.getByText('/Users/Antman/Desktop/AI_Models')).toBeInTheDocument()
    expect(screen.getByText('32k')).toBeInTheDocument()
  })

  it('keeps canonical paths on the dedicated Settings inventory only', () => {
    render(<ModelInventory
      inventory={{ model_dir: '/Users/Antman/Desktop/AI_Models', available: true, models: [{
        name: 'Qwen local', path: '/resolved/by-api/Qwen.gguf', runtime: 'gguf',
        runnable: true, architecture: 'qwen2', context_length: 32768,
        quant: 'Q4_K_M', parameter_count_b: 7, file_size_bytes: 4_000_000_000,
        readiness: 'ready_verified', readiness_reason: 'Accepted local benchmark.',
        measured_tier: 'standard', accepted_roles: ['research_chat'], route_eligible: true,
      }] }}
      health={[]}
      onRefresh={vi.fn()}
    />)

    expect(screen.getByText('/resolved/by-api/Qwen.gguf')).toBeInTheDocument()
    expect(screen.getByText('ready verified')).toBeInTheDocument()
    expect(screen.getByText('standard tier')).toBeInTheDocument()
  })
})
