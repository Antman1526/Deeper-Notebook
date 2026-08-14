import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ContextToggle } from './ContextToggle'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'common.contextModes.off': 'Off',
      'common.contextModes.insights': 'Insights',
      'common.contextModes.full': 'Full source',
      'common.contextModes.clickToCycle': 'Click to change context mode',
    })[key] ?? key,
  }),
}))

describe('ContextToggle', () => {
  it('names the icon-only control and advances the context mode once', () => {
    const onChange = vi.fn()

    render(<ContextToggle mode="off" onChange={onChange} />)

    const control = screen.getByRole('button', {
      name: 'Off: Click to change context mode',
    })
    fireEvent.click(control)

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('full')
  })
})
