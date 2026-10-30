import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { InlineEdit } from './InlineEdit'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

// The display text must wrap at spaces and move a word that does not fit to the
// next line. `break-all` split words mid-word ("wit / h") even when the next line
// had room. `break-words` fixed that but keeps each whole word as the element's
// minimum width, so in a flex row next to an actions menu the row overflowed a
// 320px screen. `overflow-wrap: anywhere` does both jobs: it only splits a word
// that cannot fit on a line of its own, and it lets the element shrink.
describe('InlineEdit wrapping', () => {
  it('uses overflow-wrap: anywhere for the display text', () => {
    render(<InlineEdit value="A browser-harness notebook with fixed evidence." onSave={vi.fn()} />)

    const display = screen.getByRole('button')
    expect(display.className).toContain('[overflow-wrap:anywhere]')
    expect(display.className).not.toContain('break-all')
    expect(display.className).not.toContain('break-words')
  })
})
