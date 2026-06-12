import { describe, it, expect } from 'vitest'
import { isNearBottom } from './ChatPanel'

/**
 * v0.8.67 (audit F5) — isNearBottom gates streaming auto-scroll so tokens don't
 * yank a user who scrolled up. Pure predicate; the DOM wiring degrades safely
 * (stickToBottomRef defaults true).
 */
describe('isNearBottom (F5)', () => {
  it('true when at the exact bottom', () => {
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 800, clientHeight: 200 })).toBe(true)
  })

  it('true when within the default 120px threshold', () => {
    // distance = 1000 - 700 - 200 = 100 < 120
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 700, clientHeight: 200 })).toBe(true)
  })

  it('false when scrolled well up (reading older messages)', () => {
    // distance = 1000 - 100 - 200 = 700 >= 120
    expect(isNearBottom({ scrollHeight: 1000, scrollTop: 100, clientHeight: 200 })).toBe(false)
  })

  it('respects a custom threshold', () => {
    // distance = 300; default(120) → false, custom(400) → true
    const el = { scrollHeight: 1000, scrollTop: 500, clientHeight: 200 }
    expect(isNearBottom(el)).toBe(false)
    expect(isNearBottom(el, 400)).toBe(true)
  })

  it('true for a short non-scrolling list (nothing to scroll)', () => {
    expect(isNearBottom({ scrollHeight: 200, scrollTop: 0, clientHeight: 200 })).toBe(true)
  })
})
