import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ErrorBoundary } from './ErrorBoundary'

function BrokenView(): never {
  throw new Error('/Users/private/failure-token')
}

describe('ErrorBoundary recovery fallback', () => {
  it('uses Recovery Center without rendering raw production exception details', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <BrokenView />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Recovery Center')
    expect(screen.queryByText(/Users|private|failure-token|Error:/i)).not.toBeInTheDocument()
    errorSpy.mockRestore()
  })

  it('preserves custom fallback props and reset behavior', () => {
    const fallback = vi.fn(({ error, resetError }: { error?: Error; resetError: () => void }) => (
      <button type="button" onClick={resetError}>
        {error?.message ?? 'custom'}
      </button>
    ))
    const { rerender } = render(
      <ErrorBoundary fallback={fallback}>
        <BrokenView />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('button')).toHaveTextContent('/Users/private/failure-token')
    // Swap the child before resetting so the broken render is not immediately
    // retried and re-captured by the same boundary.
    rerender(
      <ErrorBoundary fallback={fallback}>
        <p>Recovered</p>
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByText('Recovered')).toBeInTheDocument()
  })
})
