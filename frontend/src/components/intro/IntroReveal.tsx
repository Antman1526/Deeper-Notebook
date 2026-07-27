// v0.8.70 — "Aurora Reveal": a premium, skippable, once-per-user launch intro.
//
// Renders a full-screen overlay ABOVE the already-loaded app (mounted inside
// ConnectionGuard in app/layout.tsx, so it only appears once the backend is
// reachable and i18n is ready). The palette deliberately mirrors
// desktop/splash.py (indigo → violet → teal on a deep night background) so the
// native splash → app → reveal reads as one continuous gradient world.
//
// Once-only: a localStorage flag (`onp_intro_seen`) + a module-level guard.
// Skippable: a Skip button AND the Escape key. Reduced-motion: collapses to a
// quick fade with no long sequence. Replayable from Settings via resetIntro().
'use client'

import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { BookOpenText } from 'lucide-react'

import { useTranslation } from '@/lib/hooks/use-translation'

const INTRO_SEEN_KEY = 'onp_intro_seen'

// Survives client-side route changes within a session so it can't replay.
let _introHandledThisSession = false

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return m ? decodeURIComponent(m[1]) : null
}

function hasSeenIntro(): boolean {
  if (_introHandledThisSession) return true
  // v0.8.71 — the cookie is the source of truth. The desktop app serves the
  // frontend on a DIFFERENT dynamic port every launch, and localStorage is
  // origin-scoped (host:port) — so a localStorage flag wouldn't survive across
  // launches and the intro would replay every time. A cookie is host-scoped
  // (127.0.0.1, port-independent), so it persists like the wizard_completed
  // cookie. localStorage is kept as a same-session fallback.
  if (readCookie(INTRO_SEEN_KEY) === '1') return true
  try {
    return localStorage.getItem(INTRO_SEEN_KEY) === '1'
  } catch {
    return false
  }
}

function markIntroSeen() {
  _introHandledThisSession = true
  try {
    localStorage.setItem(INTRO_SEEN_KEY, '1')
  } catch {
    /* private mode / quota — non-fatal */
  }
  try {
    const secure = window.location.protocol === 'https:' ? '; Secure' : ''
    document.cookie =
      `${INTRO_SEEN_KEY}=1; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Strict${secure}`
  } catch {
    /* non-fatal */
  }
}

const REPLAY_EVENT = 'onp:replay-intro'

/** Re-arm the intro (used by Settings → "Replay intro"). */
export function resetIntro() {
  _introHandledThisSession = false
  try {
    localStorage.removeItem(INTRO_SEEN_KEY)
  } catch {
    /* non-fatal */
  }
  try {
    document.cookie = `${INTRO_SEEN_KEY}=; path=/; max-age=0; SameSite=Strict`
  } catch {
    /* non-fatal */
  }
}

/** Replay the intro immediately, without a page reload. */
export function replayIntro() {
  resetIntro()
  try {
    window.dispatchEvent(new Event(REPLAY_EVENT))
  } catch {
    /* non-fatal */
  }
}

// Deep "night" backdrop matching the desktop splash (var(--bg1) → var(--bg0)).
const NIGHT_BG =
  'radial-gradient(120% 120% at 18% 8%, #181a33 0%, #0d0e1d 68%)'

const AURORA = ['#6c7bff', '#b96cff', '#36c9b0'] as const

function fadeUp(reduce: boolean) {
  return {
    hidden: { opacity: 0, y: reduce ? 0 : 16 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: reduce ? 0.2 : 0.6, ease: [0.22, 1, 0.36, 1] as const },
    },
  }
}

export function IntroReveal() {
  const { t } = useTranslation()
  const reduce = useReducedMotion() ?? false
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (!hasSeenIntro()) setShow(true)
  }, [])

  // Settings → "Replay intro" dispatches this so we can re-show without a reload.
  useEffect(() => {
    const onReplay = () => setShow(true)
    window.addEventListener(REPLAY_EVENT, onReplay)
    return () => window.removeEventListener(REPLAY_EVENT, onReplay)
  }, [])

  const dismiss = useCallback(() => {
    markIntroSeen()
    setShow(false)
  }, [])

  // Auto-dismiss after the sequence; Esc skips. (Short-circuit under reduced
  // motion so we don't hold a blank-ish overlay.)
  useEffect(() => {
    if (!show) return
    const timer = window.setTimeout(dismiss, reduce ? 700 : 4400)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dismiss()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('keydown', onKey)
    }
  }, [show, reduce, dismiss])

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="onp-intro"
          role="dialog"
          aria-label="Open Notebook Plus"
          className="fixed inset-0 z-[9999] flex flex-col items-center justify-center overflow-hidden text-[#eef0ff]"
          style={{ background: NIGHT_BG }}
          initial={{ opacity: 1 }}
          exit={{
            opacity: 0,
            scale: 1.04,
            transition: { duration: reduce ? 0.2 : 0.55, ease: 'easeInOut' },
          }}
        >
          {/* Drifting aurora blobs (GPU-composited transform/opacity/filter). */}
          {AURORA.map((c, i) => {
            const pos = [
              { top: '-12%', left: '-8%' },
              { top: '6%', right: '-10%' },
              { bottom: '-18%', left: '28%' },
            ][i]
            return (
              <motion.div
                key={c}
                aria-hidden
                className="pointer-events-none absolute h-[46vmax] w-[46vmax] rounded-full"
                style={{
                  ...pos,
                  background: `radial-gradient(circle at center, ${c} 0%, transparent 62%)`,
                  filter: 'blur(60px)',
                  opacity: i === 2 ? 0.22 : 0.4,
                  willChange: 'transform',
                }}
                animate={
                  reduce
                    ? undefined
                    : { x: [0, 40, -20, 0], y: [0, -30, 25, 0], scale: [1, 1.12, 1.04, 1] }
                }
                transition={
                  reduce
                    ? undefined
                    : { duration: 16 + i * 4, repeat: Infinity, ease: 'easeInOut' }
                }
              />
            )
          })}

          {/* Foreground brand stack. */}
          <motion.div
            className="relative flex flex-col items-center px-6 text-center"
            initial="hidden"
            animate="show"
            variants={{
              hidden: {},
              show: {
                transition: {
                  staggerChildren: reduce ? 0 : 0.16,
                  delayChildren: reduce ? 0 : 0.15,
                },
              },
            }}
          >
            <motion.div
              variants={{
                hidden: { opacity: 0, scale: reduce ? 1 : 0.55, rotate: reduce ? 0 : -8 },
                show: {
                  opacity: 1,
                  scale: 1,
                  rotate: 0,
                  transition: reduce
                    ? { duration: 0.2 }
                    : { type: 'spring', stiffness: 190, damping: 16 },
                },
              }}
              className="mb-7 grid h-24 w-24 place-items-center rounded-[1.4rem]"
              style={{
                background: `linear-gradient(135deg, ${AURORA[0]}, ${AURORA[1]})`,
                boxShadow: `0 24px 70px -14px ${AURORA[1]}99`,
              }}
            >
              <BookOpenText className="h-12 w-12" strokeWidth={1.6} color="#fff" />
            </motion.div>

            <motion.h1
              variants={fadeUp(reduce)}
              className="text-5xl font-semibold tracking-tight sm:text-6xl"
            >
              Open Notebook<span className="dn-aurora-text">+</span>
            </motion.h1>

            <motion.p variants={fadeUp(reduce)} className="mt-3 text-lg text-[#c5c9ef]">
              {t('intro.tagline', { defaultValue: 'Your private research brain' })}
            </motion.p>

            {/* Progress sweep. */}
            <motion.div
              variants={fadeUp(reduce)}
              className="relative mt-9 h-1 w-56 overflow-hidden rounded-full"
              style={{ background: 'rgba(255,255,255,0.12)' }}
            >
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{ background: `linear-gradient(90deg, ${AURORA[0]}, ${AURORA[1]}, ${AURORA[2]})` }}
                initial={{ width: '0%' }}
                animate={{ width: '100%' }}
                transition={{ duration: reduce ? 0.2 : 3.6, ease: 'easeInOut' }}
              />
            </motion.div>
          </motion.div>

          {/* Skip — also Esc. */}
          <motion.button
            type="button"
            onClick={dismiss}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { delay: reduce ? 0 : 0.8 } }}
            className="absolute bottom-8 right-8 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-sm text-[#c5c9ef] backdrop-blur transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
          >
            {t('intro.skip', { defaultValue: 'Skip' })} →
          </motion.button>

          <p className="absolute bottom-8 left-8 flex items-center gap-2 text-xs text-[#8a90c0]">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#36c9b0]" />
            {t('intro.privacy', { defaultValue: 'Everything runs on your Mac — no cloud required.' })}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
