import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ResearchCoreHeader } from './ResearchCoreHeader'

describe('ResearchCoreHeader', () => {
  it('discloses workspace status and safe local readiness details semantically', () => {
    render(
      <ResearchCoreHeader
        workspaceTitle="Research Core"
        authoritySummary={{ appOwned: 2, externalReadOnly: 4 }}
        saveState="Saved locally"
        readiness={{
          state: 'ready',
          detail: 'Two local models are ready from /Users/Antman/Desktop/MacBook AI models',
          models: [{ id: 'qwen-research', provider: 'MLX', path: '/Users/Antman/Desktop/MacBook AI models/qwen' }],
        }}
        memoryPressure={{ state: 'elevated', detail: 'Memory pressure elevated' }}
        queuedWorkCount={3}
      />,
    )

    const header = screen.getByRole('banner', { name: 'Research Core workspace' })
    expect(header).toHaveTextContent('Research Core')
    expect(header).toHaveTextContent('2 app-owned')
    expect(header).toHaveTextContent('4 external read-only')
    expect(header).toHaveTextContent('Saved locally')
    expect(header).toHaveTextContent('Local readiness: ready')
    expect(header).toHaveTextContent('Memory pressure elevated')
    expect(header).toHaveTextContent('3 queued')

    const readiness = screen.getByRole('button', { name: /Local readiness: ready — Two local models are ready/ })
    fireEvent.click(readiness)
    expect(screen.getByRole('listitem')).toHaveTextContent('qwen-research')
    expect(screen.getByRole('listitem')).toHaveTextContent('MLX')
    expect(header).not.toHaveTextContent('/Users/Antman/Desktop/MacBook AI models/qwen')
    expect(header).not.toHaveTextContent('/Users/Antman/Desktop/MacBook AI models')
  })
})
