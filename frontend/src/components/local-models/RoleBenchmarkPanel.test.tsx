import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { RoleBenchmarkPanel } from './RoleBenchmarkPanel'

// Echo interpolation values so each role's benchmark button stays addressable by its own label.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key} ${JSON.stringify(options)}` : key),
  }),
}))

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

    expect(screen.getByText('settings.roleBenchmarkPanel.speedOnlyLegacy')).toBeInTheDocument()
    expect(screen.getByText('settings.roleBenchmarkPanel.notMeasured')).toBeInTheDocument()
  })

  it('starts an individual role benchmark', () => {
    const onBenchmarkRole = vi.fn()
    render(<RoleBenchmarkPanel onBenchmarkAll={vi.fn()} onBenchmarkRole={onBenchmarkRole} />)

    fireEvent.click(screen.getByRole('button', { name: 'settings.roleBenchmarkPanel.benchmarkRoleAria {"label":"settings.roleBenchmarkPanel.roleChat"}' }))
    expect(onBenchmarkRole).toHaveBeenCalledWith('chat')
  })
})
