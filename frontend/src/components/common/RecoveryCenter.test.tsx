import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RecoveryCenter } from './RecoveryCenter'

type RecoveryWindow = Window & {
  DN?: { relaunch?: () => boolean }
  ONP?: { relaunch?: () => boolean }
}

describe('RecoveryCenter', () => {
  const reload = vi.fn()
  const writeText = vi.fn()

  beforeEach(() => {
    reload.mockReset()
    writeText.mockReset().mockResolvedValue(undefined)
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { reload },
    })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    delete (window as RecoveryWindow).DN
    delete (window as RecoveryWindow).ONP
  })

  afterEach(() => {
    delete (window as RecoveryWindow).DN
    delete (window as RecoveryWindow).ONP
  })

  it('renders safe semantic recovery actions without exception details', () => {
    const resetError = vi.fn()
    render(<RecoveryCenter resetError={resetError} error={new Error('/Users/private/token=secret')} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Recovery Center')
    expect(screen.queryByText(/Users|private|token|secret|Error:/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Copy diagnostic code' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    fireEvent.click(screen.getByRole('button', { name: 'Reload page' }))
    fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostic code' }))

    expect(resetError).toHaveBeenCalledOnce()
    expect(reload).toHaveBeenCalledOnce()
    expect(writeText).toHaveBeenCalledWith('DN-UI-RECOVERY')
  })

  it('offers explicit relaunch only when a desktop bridge exists', () => {
    const relaunch = vi.fn(() => true)
    ;(window as RecoveryWindow).DN = { relaunch }
    render(<RecoveryCenter resetError={vi.fn()} />)

    const button = screen.getByRole('button', { name: 'Relaunch desktop app' })
    expect(relaunch).not.toHaveBeenCalled()
    fireEvent.click(button)
    expect(relaunch).toHaveBeenCalledOnce()
  })

  it('handles unavailable clipboard and bridge APIs without throwing', () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
    render(<RecoveryCenter resetError={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Copy diagnostic code' }))
    expect(screen.getByRole('status')).toHaveTextContent('Copy unavailable')
    expect(screen.queryByRole('button', { name: 'Relaunch desktop app' })).not.toBeInTheDocument()
  })
})
