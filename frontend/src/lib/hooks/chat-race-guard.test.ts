// v0.8.21 — Contract test for the message-sync race guard added to
// useSourceChat.ts and useNotebookChat.ts.
//
// Background (see CHANGELOG v0.8.21 + the inline comments in the
// hooks): both chat hooks had a useEffect that overwrote local
// messages with `currentSession.messages` on every refetch. When a
// user sent msg #2 while msg #1's stream-complete refetch was still
// in flight, the refetch returned `[user_1, ai_1]` and clobbered
// msg #2's optimistic user bubble and streaming AI placeholder.
//
// The fix: an `inFlightSendsRef = useRef(0)` counter, incremented
// at the start of `sendMessage` and decremented in `finally{}`. The
// useEffect now skips its `setMessages(currentSession.messages)`
// when the counter is > 0.
//
// A boolean would NOT have been enough — msg #1's finally{} runs
// while msg #2 is still in flight, and a boolean would get cleared
// at that point, reopening the race for msg #2. The counter is
// load-bearing.
//
// This file is a source-text assertion: a future refactor that drops
// the counter, replaces it with a boolean, or moves the increment/
// decrement to the wrong place fails this test loudly. It does NOT
// run the full hook integration because the existing test scaffolding
// (use-deep-health.test.ts) only covers single-API-call hooks — a
// proper streaming-send simulation would need a sizable mock harness
// out of scope for this fix.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const HOOKS = ['useSourceChat.ts', 'useNotebookChat.ts'] as const

describe('v0.8.21 chat race guard', () => {
  for (const hook of HOOKS) {
    describe(hook, () => {
      const src = readFileSync(join(__dirname, hook), 'utf-8')

      it('declares an inFlightSendsRef counter (not a boolean)', () => {
        expect(
          src,
          `${hook}: must declare inFlightSendsRef = useRef(0). A ` +
          `boolean is insufficient — msg #1's finally{} would clear ` +
          `it while msg #2 is still in flight, reopening the race.`,
        ).toMatch(/const\s+inFlightSendsRef\s*=\s*useRef\(0\)/)
      })

      it('gates the message-sync useEffect on counter === 0', () => {
        expect(
          src,
          `${hook}: the useEffect that overwrites messages from ` +
          `currentSession must skip when inFlightSendsRef.current > 0. ` +
          `Without the guard, a refetch landing mid-second-send wipes ` +
          `the second send's optimistic user bubble.`,
        ).toMatch(/inFlightSendsRef\.current\s*===\s*0/)
      })

      it('increments the counter inside sendMessage', () => {
        expect(
          src,
          `${hook}: sendMessage must arm the guard with ` +
          `'inFlightSendsRef.current += 1' BEFORE any await. ` +
          `Missing this means the guard is never armed and the race ` +
          `is reintroduced.`,
        ).toMatch(/inFlightSendsRef\.current\s*\+=\s*1/)
      })

      it('decrements the counter (Math.max guarded)', () => {
        expect(
          src,
          `${hook}: finally{} must decrement the counter with ` +
          `'inFlightSendsRef.current = Math.max(0, ... - 1)'. ` +
          `The Math.max defends against the (purely defensive) ` +
          `underflow case if a future refactor accidentally double- ` +
          `decrements.`,
        ).toMatch(
          /inFlightSendsRef\.current\s*=\s*Math\.max\(\s*0,\s*inFlightSendsRef\.current\s*-\s*1\s*,?\s*\)/,
        )
      })

      it('comments reference v0.8.21 so the rationale survives blame', () => {
        // Keeps the audit-trail comment alive — a refactor that drops
        // the inline v0.8.21 markers would also need to update this
        // test, forcing a conscious decision about removing the guard.
        const matches = src.match(/v0\.8\.21/g) ?? []
        expect(
          matches.length,
          `${hook}: expected ≥2 'v0.8.21' markers (ref decl + at ` +
          `least one of the touch sites). Got ${matches.length}.`,
        ).toBeGreaterThanOrEqual(2)
      })
    })
  }
})
