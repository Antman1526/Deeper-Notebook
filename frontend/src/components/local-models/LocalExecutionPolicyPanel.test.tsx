import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LocalExecutionPolicyPanel } from './LocalExecutionPolicyPanel'

describe('LocalExecutionPolicyPanel', () => {
  it('keeps Local Preferred unchanged when cloud confirmation is cancelled', () => {
    const onSave = vi.fn()
    render(<LocalExecutionPolicyPanel
      policy="strict_local"
      computeProfile="balanced"
      memoryLimitBytes={8 * 1024 ** 3}
      onSave={onSave}
    />)

    fireEvent.click(screen.getByRole('button', { name: 'Use Local Preferred' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('stage')
    expect(screen.getByRole('alertdialog')).toHaveTextContent('content class')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByText('Strict Local')).toBeInTheDocument()
  })

  it('does not allow Strict Local to be saved with a cloud route', () => {
    const onSave = vi.fn()
    render(<LocalExecutionPolicyPanel
      policy="strict_local"
      computeProfile="balanced"
      memoryLimitBytes={0}
      cloudRouteRequested
      onSave={onSave}
    />)

    expect(screen.getByText('Strict Local blocks cloud routes.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save local execution policy' })).toBeDisabled()
  })
})
