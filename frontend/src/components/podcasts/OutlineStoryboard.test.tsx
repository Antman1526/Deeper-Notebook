import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { OutlineStoryboard } from './OutlineStoryboard'

describe('OutlineStoryboard', () => {
  it('reorders with keyboard buttons, preserves focus, and announces position', () => {
    const onChange = vi.fn()
    render(<OutlineStoryboard segments={['Introduction', 'Findings', 'Takeaway']} onChange={onChange} />)

    const moveEarlier = screen.getByRole('button', { name: 'Move Findings earlier' })
    fireEvent.click(moveEarlier)

    expect(onChange).toHaveBeenCalledWith(['Findings', 'Introduction', 'Takeaway'])
    expect(document.activeElement).toBe(moveEarlier)
    expect(screen.getByRole('status')).toHaveTextContent('Findings moved to position 1')
  })

  it('supports drag reorder and keeps a moved segment actionable', () => {
    const onChange = vi.fn()
    render(<OutlineStoryboard segments={['One', 'Two', 'Three']} onChange={onChange} />)

    const source = screen.getByRole('listitem', { name: 'Two' })
    const target = screen.getByRole('listitem', { name: 'One' })
    fireEvent.dragStart(source)
    fireEvent.dragOver(target)
    fireEvent.drop(target)

    expect(onChange).toHaveBeenCalledWith(['Two', 'One', 'Three'])
  })

  it('preserves controlled segment objects while reordering', () => {
    const onChange = vi.fn()
    const segments = [{ id: 'one', title: 'One' }, { id: 'two', title: 'Two' }]
    render(<OutlineStoryboard segments={segments} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Move Two earlier' }))

    expect(onChange).toHaveBeenCalledWith([segments[1], segments[0]])
  })
})
