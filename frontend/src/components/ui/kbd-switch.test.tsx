import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Kbd } from './kbd'
import { Switch } from './switch'

describe('Kbd', () => {
  it('renders a keyboard key with the shared chip styling', () => {
    render(<Kbd>⌘K</Kbd>)
    const key = screen.getByText('⌘K')
    expect(key.tagName).toBe('KBD')
    expect(key).toHaveAttribute('data-slot', 'kbd')
    // The 12px type floor applies to shortcut chips too (one was 10px).
    expect(key).toHaveClass('text-xs')
  })

  it('merges a caller class', () => {
    render(<Kbd className="dn-command-shortcut">K</Kbd>)
    expect(screen.getByText('K')).toHaveClass('dn-command-shortcut', 'font-mono')
  })
})

function ControlledSwitch({ onChange }: { onChange?: (value: boolean) => void }) {
  const [checked, setChecked] = useState(false)
  return (
    <Switch
      aria-label="Guided tips"
      checked={checked}
      onCheckedChange={(value) => {
        setChecked(value)
        onChange?.(value)
      }}
    />
  )
}

describe('Switch', () => {
  it('is announced as a switch with its state', () => {
    render(<ControlledSwitch />)
    const control = screen.getByRole('switch', { name: 'Guided tips' })
    expect(control).toHaveAttribute('aria-checked', 'false')
    expect(control).toHaveAttribute('data-state', 'unchecked')
  })

  it('toggles on click and reports the new value', () => {
    const onChange = vi.fn()
    render(<ControlledSwitch onChange={onChange} />)
    const control = screen.getByRole('switch', { name: 'Guided tips' })
    fireEvent.click(control)
    expect(onChange).toHaveBeenLastCalledWith(true)
    expect(control).toHaveAttribute('aria-checked', 'true')
    expect(control).toHaveAttribute('data-state', 'checked')
  })

  it('is a native button, so Space and Enter toggle it without custom key handling', () => {
    render(<ControlledSwitch />)
    expect(screen.getByRole('switch', { name: 'Guided tips' }).tagName).toBe('BUTTON')
  })

  it('does not toggle when disabled', () => {
    const onCheckedChange = vi.fn()
    render(<Switch aria-label="Off" checked={false} onCheckedChange={onCheckedChange} disabled />)
    fireEvent.click(screen.getByRole('switch', { name: 'Off' }))
    expect(onCheckedChange).not.toHaveBeenCalled()
  })

  it('is a submit-safe button', () => {
    render(<Switch aria-label="Safe" checked={false} onCheckedChange={() => {}} />)
    expect(screen.getByRole('switch', { name: 'Safe' })).toHaveAttribute('type', 'button')
  })
})
