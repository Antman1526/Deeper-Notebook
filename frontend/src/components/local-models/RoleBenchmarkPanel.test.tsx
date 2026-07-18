import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { RoleBenchmarkPanel } from './RoleBenchmarkPanel'

describe('RoleBenchmarkPanel', () => {
  it('labels a legacy speed-only result as not quality measured', () => {
    render(
      <RoleBenchmarkPanel
        benchmark={{
          job_id: 'legacy', roles: ['chat'], status: 'completed', results: [{
            role: 'chat', label: 'Default chat', status: 'completed', score: 82,
            model_name: 'old-local', latency_ms: 100, tokens_per_second: 40,
          }],
        }}
        onBenchmarkAll={vi.fn()}
        onBenchmarkRole={vi.fn()}
      />,
    )

    expect(screen.getByText(/speed-only legacy result/i)).toBeInTheDocument()
    expect(screen.getByText('Not measured')).toBeInTheDocument()
  })

  it('starts an individual role benchmark', () => {
    const onBenchmarkRole = vi.fn()
    render(<RoleBenchmarkPanel onBenchmarkAll={vi.fn()} onBenchmarkRole={onBenchmarkRole} />)

    fireEvent.click(screen.getByRole('button', { name: /benchmark default chat/i }))
    expect(onBenchmarkRole).toHaveBeenCalledWith('chat')
  })
})
