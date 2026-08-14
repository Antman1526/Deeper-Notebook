import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LocalExecutionPolicyPanel } from './LocalExecutionPolicyPanel'

describe('LocalExecutionPolicyPanel', () => {
  it('keeps a pending cloud route unchanged when its route-specific confirmation is cancelled', () => {
    const onSave = vi.fn()
    const onConfirmCloudRoute = vi.fn()
    render(<LocalExecutionPolicyPanel
      policy="local_preferred"
      computeProfile="balanced"
      memoryLimitBytes={8 * 1024 ** 3}
      pendingCloudRoute={{ stage: 'Research Chat', contentClass: 'Selected knowledge' }}
      onSave={onSave}
      onConfirmCloudRoute={onConfirmCloudRoute}
    />)

    fireEvent.click(screen.getByRole('button', { name: 'Review pending cloud fallback' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Research Chat')
    expect(screen.getByRole('button', { name: 'Confirm cloud continuation' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onSave).not.toHaveBeenCalled()
    expect(onConfirmCloudRoute).not.toHaveBeenCalled()
  })

  it('requires matching route stage and content class before recording a cloud continuation', () => {
    const onConfirmCloudRoute = vi.fn()
    render(<LocalExecutionPolicyPanel
      policy="local_preferred" computeProfile="maximum_quality" memoryLimitBytes={0}
      pendingCloudRoute={{ stage: 'Evidence', contentClass: 'External evidence summary' }}
      onConfirmCloudRoute={onConfirmCloudRoute} onSave={vi.fn()}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'Review pending cloud fallback' }))
    fireEvent.change(screen.getByLabelText('stage'), { target: { value: 'Evidence' } })
    fireEvent.change(screen.getByLabelText('content class'), { target: { value: 'External evidence summary' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm cloud continuation' }))
    expect(onConfirmCloudRoute).toHaveBeenCalledWith({ stage: 'Evidence', contentClass: 'External evidence summary' })
  })

  it('clears valid cancelled entries before the pending route dialog is reopened', () => {
    render(<LocalExecutionPolicyPanel
      policy="local_preferred" computeProfile="balanced" memoryLimitBytes={0}
      pendingCloudRoute={{ stage: 'Research Chat', contentClass: 'Selected knowledge' }} onConfirmCloudRoute={vi.fn()} onSave={vi.fn()}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'Review pending cloud fallback' }))
    fireEvent.change(screen.getByLabelText('stage'), { target: { value: 'Research Chat' } })
    fireEvent.change(screen.getByLabelText('content class'), { target: { value: 'Selected knowledge' } })
    expect(screen.getByRole('button', { name: 'Confirm cloud continuation' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review pending cloud fallback' }))
    expect(screen.getByLabelText('stage')).toHaveValue('')
    expect(screen.getByLabelText('content class')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Confirm cloud continuation' })).toBeDisabled()
  })

  it('does not offer cloud continuation under Strict Local', () => {
    const onSave = vi.fn()
    render(<LocalExecutionPolicyPanel
      policy="strict_local"
      computeProfile="balanced"
      memoryLimitBytes={0}
      pendingCloudRoute={{ stage: 'Research Chat', contentClass: 'Selected knowledge' }}
      onSave={onSave}
    />)

    expect(screen.getByText('Strict Local blocks cloud routes.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Review pending cloud fallback' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save local execution policy' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Save local execution policy' })).toHaveClass(
      'w-full',
      'whitespace-normal',
      'sm:w-auto',
    )
  })
})
