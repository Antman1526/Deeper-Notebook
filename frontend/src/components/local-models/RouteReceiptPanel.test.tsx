import React from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { RouteReceiptPanel } from './RouteReceiptPanel'

describe('RouteReceiptPanel', () => {
  it('shows the chosen model and one permitted fallback without prompt content', () => {
    render(
      <RouteReceiptPanel
        receipts={[{
          role: 'source_synthesis', selected_model_id: 'model:qwen',
          fallback_model_id: 'model:llama', benchmark_age_seconds: 60,
          reason: 'fresh measured quality winner', outcome: 'selected',
        }]}
        isLoading={false}
        isError={false}
      />,
    )

    expect(screen.getByText('model:qwen')).toBeInTheDocument()
    expect(screen.getByText('model:llama')).toBeInTheDocument()
    expect(screen.getByText(/source synthesis/i)).toBeInTheDocument()
  })

  it('keeps an unavailable receipt endpoint quiet and explicit', () => {
    render(<RouteReceiptPanel receipts={[]} isLoading={false} isError />)
    expect(screen.getByText(/not exposed by this runtime/i)).toBeInTheDocument()
  })
})
