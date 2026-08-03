import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
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

  it('keeps duplicate labels independently addressable during keyboard reorder', () => {
    function ControlledStoryboard() {
      const [segments, setSegments] = useState(['Intro', 'Intro', 'Takeaway'])
      return <OutlineStoryboard
        segments={segments}
        onChange={(next) => setSegments(next.map((segment) => typeof segment === 'string' ? segment : segment.title ?? segment.name ?? segment.id ?? 'Untitled segment'))}
      />
    }
    render(<ControlledStoryboard />)

    const beforeIds = screen.getAllByRole('listitem').map((item) => item.getAttribute('data-segment-id'))
    expect(new Set(beforeIds).size).toBe(3)
    const duplicateMoveLater = screen.getAllByRole('button', { name: 'Move Intro later' })[0]
    fireEvent.click(duplicateMoveLater)

    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      expect.stringContaining('Intro'), expect.stringContaining('Intro'), expect.stringContaining('Takeaway'),
    ])
    expect(screen.getByRole('status')).toHaveTextContent('Intro moved to position 2')
    expect(screen.getAllByRole('listitem').map((item) => item.getAttribute('data-segment-id'))).toEqual([
      beforeIds[1], beforeIds[0], beforeIds[2],
    ])
    expect(document.activeElement).toHaveAttribute('aria-label', 'Move Intro later')
  })
})
