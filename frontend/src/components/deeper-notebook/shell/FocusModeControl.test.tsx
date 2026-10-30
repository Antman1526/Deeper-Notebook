import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { FocusModeControl } from './FocusModeControl'
import { DEFAULT_DISPLAY_PREFERENCES, useDisplayPreferencesStore } from '@/lib/stores/display-preferences-store'

describe('FocusModeControl', () => {
  beforeEach(() => {
    useDisplayPreferencesStore.setState(DEFAULT_DISPLAY_PREFERENCES)
    document.documentElement.dataset.dnFocusMode = 'false'
  })

  it('exposes explicit pressed semantics and a reversible toggle', () => {
    render(<FocusModeControl />)

    const control = screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.enterFocusMode' })
    expect(control).toHaveAttribute('aria-pressed', 'false')
    expect(control).toHaveClass('motion-reduce:transition-none')

    fireEvent.click(control)

    const exit = screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.exitFocusMode' })
    expect(exit).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.dataset.dnFocusMode).toBe('true')
  })

  it('activates with the documented primary shortcut but ignores editable fields', () => {
    render(<FocusModeControl />)
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    fireEvent.keyDown(input, { key: 'f', ctrlKey: true, shiftKey: true })
    expect(screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.enterFocusMode' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'f', ctrlKey: true, shiftKey: true })
    expect(screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.exitFocusMode' })).toBeInTheDocument()
    input.remove()
  })

  it('uses Escape as an exit-only action and keeps the active exit control focusable', () => {
    render(<FocusModeControl />)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.enterFocusMode' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.enterFocusMode' }))
    const exit = screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.exitFocusMode' })
    exit.focus()
    expect(exit).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByRole('button', { name: 'workspace.displayPreferencesPanel.enterFocusMode' })).toBeInTheDocument()
  })
})
