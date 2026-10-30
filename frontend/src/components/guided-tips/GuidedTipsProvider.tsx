'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { usePathname } from 'next/navigation'

import { getGuidedTipForPath } from '@/lib/guided-tips/catalog'
import { useGuidedTipsStore } from '@/lib/stores/guided-tips-store'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'

const CALLOUT_WIDTH = 320
const VIEWPORT_INSET = 16
const ANCHOR_GAP = 12
const POINTER_INSET = 12
const POINTER_SIZE = 10
const ACTIVE_ATTRIBUTE = 'data-guided-tip-active'
const SUSPEND_SELECTOR = '[aria-modal="true"], [data-guided-tips-suspend="true"]'

// v0.8.130 — the callout can be pushed below the page heading, away from the navigation item
// it describes, so the anchor carries a ring (outline only: layout never shifts) and the
// callout draws a pointer only when it really sits beside the anchor. Rendered as a <style>
// next to the callout rather than a .css import: Vitest's PostCSS config cannot load in
// this repo's unit-test setup, and the rules only matter while a tip is on screen.
const GUIDED_TIP_STYLES = `
[data-guided-tip-active='true'] {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
  border-radius: var(--radius-md);
}
@media (prefers-reduced-motion: no-preference) {
  [data-guided-tip-active='true'] {
    animation: guided-tip-ring-in 240ms ease-out 1 both;
  }
  @keyframes guided-tip-ring-in {
    from { outline-color: transparent; }
    to { outline-color: var(--primary); }
  }
}
.guided-tip-pointer {
  position: absolute;
  left: -6px;
  width: ${POINTER_SIZE}px;
  height: ${POINTER_SIZE}px;
  background: var(--card);
  border-style: solid;
  border-color: var(--border);
  border-width: 0 0 1px 1px;
  transform: rotate(45deg);
  pointer-events: none;
}
`

interface TipPosition {
  top: number
  left: number
}

interface TipPlacement extends TipPosition {
  pointer: { top: number } | null
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

interface PlainRect {
  top: number
  left: number
  right: number
  bottom: number
}

// v0.8.130 — the callout sits right of its rail anchor, and the rail ends where the main
// column (and its <h1>) begins, so the callout covered the page title. Keep it beside the
// anchor, but if it would touch the heading (closer than ANCHOR_GAP counts as touching)
// slide it down to just below the heading. Staying on screen wins over clearing the
// heading, so the viewport clamp runs last. Pure and rect-based because jsdom has no layout.
export function placeCallout({
  anchor,
  heading,
  calloutHeight,
  viewport,
}: {
  anchor: PlainRect
  heading: PlainRect | null
  calloutHeight: number
  viewport: { width: number; height: number }
}): TipPlacement {
  const maxTop = Math.max(VIEWPORT_INSET, viewport.height - calloutHeight - VIEWPORT_INSET)
  const left = clamp(
    anchor.right + ANCHOR_GAP,
    VIEWPORT_INSET,
    Math.max(VIEWPORT_INSET, viewport.width - CALLOUT_WIDTH - VIEWPORT_INSET),
  )
  const top = clamp(anchor.top, VIEWPORT_INSET, maxTop)

  const touchesHeading =
    heading !== null
    && left < heading.right + ANCHOR_GAP
    && left + CALLOUT_WIDTH + ANCHOR_GAP > heading.left
    && top < heading.bottom + ANCHOR_GAP
    && top + calloutHeight + ANCHOR_GAP > heading.top

  const placedTop = touchesHeading
    ? clamp(heading.bottom + ANCHOR_GAP, VIEWPORT_INSET, maxTop)
    : top

  return { top: placedTop, left, pointer: pointFromCallout(anchor, placedTop, left, calloutHeight) }
}

// v0.8.130 — a pointer is only drawn while the callout truly sits beside its anchor: to the
// right of it and spanning its vertical centre. Pushed below the heading or clamped away,
// it would point at nothing, so the ring on the anchor does the pointing instead.
function pointFromCallout(
  anchor: PlainRect,
  top: number,
  left: number,
  calloutHeight: number,
): { top: number } | null {
  const centre = (anchor.top + anchor.bottom) / 2

  if (left < anchor.right || centre < top || centre > top + calloutHeight) {
    return null
  }

  return {
    top: clamp(centre - top, POINTER_INSET, Math.max(POINTER_INSET, calloutHeight - POINTER_INSET)),
  }
}

function findMainHeading(callout: HTMLElement | null): PlainRect | null {
  const heading =
    document.querySelector<HTMLElement>('main h1') ?? document.querySelector<HTMLElement>('h1')

  if (!heading || callout?.contains(heading)) {
    return null
  }

  const rect = heading.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0 ? rect : null
}

export function GuidedTipsProvider() {
  const { t } = useTranslation()
  const pathname = usePathname()
  const enabled = useGuidedTipsStore((state) => state.enabled)
  const completed = useGuidedTipsStore((state) => state.completed)
  const complete = useGuidedTipsStore((state) => state.complete)
  const setEnabled = useGuidedTipsStore((state) => state.setEnabled)
  const [position, setPosition] = useState<TipPlacement | null>(null)
  const calloutRef = useRef<HTMLElement>(null)

  const tip = useMemo(() => getGuidedTipForPath(pathname ?? ''), [pathname])
  const isComplete = tip ? (completed[tip.id] ?? 0) >= tip.version : true

  useEffect(() => {
    if (!tip || !enabled || isComplete) {
      setPosition(null)
      return
    }

    const activeTip = tip
    // v0.8.130 — the element currently carrying data-guided-tip-active. Every path that
    // hides the tip (suspend, missing anchor, dismiss, unmount) funnels through this, and the
    // effect cleanup clears it, so the ring can never be left behind.
    let markedAnchor: HTMLElement | null = null

    const mark = (anchor: HTMLElement | null) => {
      if (markedAnchor === anchor) {
        return
      }
      markedAnchor?.removeAttribute(ACTIVE_ATTRIBUTE)
      anchor?.setAttribute(ACTIVE_ATTRIBUTE, 'true')
      markedAnchor = anchor
    }

    const updatePosition = () => {
      if (document.querySelector(SUSPEND_SELECTOR)) {
        mark(null)
        setPosition(null)
        return
      }

      const anchor = document.querySelector<HTMLElement>(
        `[data-guided-tip-anchor="${activeTip.anchor}"]`,
      )

      if (!anchor) {
        mark(null)
        setPosition(null)
        return
      }

      mark(anchor)
      const anchorRect = anchor.getBoundingClientRect()
      const calloutHeight = calloutRef.current?.getBoundingClientRect().height ?? 180
      setPosition(
        placeCallout({
          anchor: anchorRect,
          heading: findMainHeading(calloutRef.current),
          calloutHeight,
          viewport: { width: window.innerWidth, height: window.innerHeight },
        }),
      )
    }

    const observer = new MutationObserver(updatePosition)
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['aria-modal', 'data-guided-tips-suspend', 'data-guided-tip-anchor'],
    })
    window.addEventListener('resize', updatePosition)
    document.addEventListener('scroll', updatePosition, true)
    document.addEventListener('keydown', handleKeyDown)
    updatePosition()

    function handleKeyDown(event: KeyboardEvent) {
      const anchor = document.querySelector<HTMLElement>(
        `[data-guided-tip-anchor="${activeTip.anchor}"]`,
      )

      if (
        event.key === 'Escape'
        && calloutRef.current
        && anchor
        && !document.querySelector(SUSPEND_SELECTOR)
      ) {
        complete(activeTip)
        setPosition(null)
      }
    }

    return () => {
      mark(null)
      observer.disconnect()
      window.removeEventListener('resize', updatePosition)
      document.removeEventListener('scroll', updatePosition, true)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [complete, enabled, isComplete, tip])

  if (!tip || !position) {
    return null
  }

  const dismiss = () => {
    complete(tip)
    setPosition(null)
  }

  const disable = () => {
    setEnabled(false)
    setPosition(null)
  }

  // v0.8.130 — portalled to <body>: inside the shell its z-index only counted within the
  // navigator's stacking context, so page controls painted over the buttons.
  return createPortal(
    <>
    <style>{GUIDED_TIP_STYLES}</style>
    <aside
      ref={calloutRef}
      role="note"
      aria-label={t('workspace.guidedTipsProvider.ariaLabel', { title: t(tip.titleKey) })}
      className="w-80 rounded-lg border bg-card p-4 text-card-foreground shadow-lg"
      style={{ position: 'fixed', top: position.top, left: position.left, zIndex: 50 }}
    >
      {position.pointer ? (
        <span
          aria-hidden="true"
          data-guided-tip-pointer=""
          className="guided-tip-pointer"
          style={{ top: position.pointer.top - POINTER_SIZE / 2 }}
        />
      ) : null}
      <p className="text-sm font-medium">{t(tip.titleKey)}</p>
      <p className="mt-1 text-sm text-muted-foreground">{t(tip.bodyKey)}</p>
      <div className="mt-3 flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={disable}>
          {t('workspace.guidedTipsProvider.dontShowAgain')}
        </Button>
        <Button type="button" size="sm" onClick={dismiss}>
          {t('workspace.guidedTipsProvider.gotIt')}
        </Button>
      </div>
    </aside>
    </>,
    document.body,
  )
}
