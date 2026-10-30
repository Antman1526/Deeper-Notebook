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

    fireEvent.click(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.reviewPendingCloudFallback' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Research Chat')
    expect(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.confirmAction' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }))

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
    fireEvent.click(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.reviewPendingCloudFallback' }))
    fireEvent.change(screen.getByLabelText('settings.localExecutionPolicyPanel.stageAria'), { target: { value: 'Evidence' } })
    fireEvent.change(screen.getByLabelText('settings.localExecutionPolicyPanel.contentClassAria'), { target: { value: 'External evidence summary' } })
    fireEvent.click(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.confirmAction' }))
    expect(onConfirmCloudRoute).toHaveBeenCalledWith({ stage: 'Evidence', contentClass: 'External evidence summary' })
  })

  it('clears valid cancelled entries before the pending route dialog is reopened', () => {
    render(<LocalExecutionPolicyPanel
      policy="local_preferred" computeProfile="balanced" memoryLimitBytes={0}
      pendingCloudRoute={{ stage: 'Research Chat', contentClass: 'Selected knowledge' }} onConfirmCloudRoute={vi.fn()} onSave={vi.fn()}
    />)
    fireEvent.click(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.reviewPendingCloudFallback' }))
    fireEvent.change(screen.getByLabelText('settings.localExecutionPolicyPanel.stageAria'), { target: { value: 'Research Chat' } })
    fireEvent.change(screen.getByLabelText('settings.localExecutionPolicyPanel.contentClassAria'), { target: { value: 'Selected knowledge' } })
    expect(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.confirmAction' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.reviewPendingCloudFallback' }))
    expect(screen.getByLabelText('settings.localExecutionPolicyPanel.stageAria')).toHaveValue('')
    expect(screen.getByLabelText('settings.localExecutionPolicyPanel.contentClassAria')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.confirmAction' })).toBeDisabled()
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

    expect(screen.getByText('settings.localExecutionPolicyPanel.strictBlocksCloud')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'settings.localExecutionPolicyPanel.reviewPendingCloudFallback' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.save' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'settings.localExecutionPolicyPanel.save' })).toHaveClass(
      'w-full',
      'whitespace-normal',
      'sm:w-auto',
    )
  })
})
