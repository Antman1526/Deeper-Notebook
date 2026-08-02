'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'

import { getGuidedTipForPath } from '@/lib/guided-tips/catalog'
import { useGuidedTipsStore } from '@/lib/stores/guided-tips-store'
import { Button } from '@/components/ui/button'

const CALLOUT_WIDTH = 320
const VIEWPORT_INSET = 16
const ANCHOR_GAP = 12
const SUSPEND_SELECTOR = '[aria-modal="true"], [data-guided-tips-suspend="true"]'

interface TipPosition {
  top: number
  left: number
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

export function GuidedTipsProvider() {
  const pathname = usePathname()
  const enabled = useGuidedTipsStore((state) => state.enabled)
  const completed = useGuidedTipsStore((state) => state.completed)
  const complete = useGuidedTipsStore((state) => state.complete)
  const setEnabled = useGuidedTipsStore((state) => state.setEnabled)
  const [position, setPosition] = useState<TipPosition | null>(null)
  const calloutRef = useRef<HTMLElement>(null)

  const tip = useMemo(() => getGuidedTipForPath(pathname ?? ''), [pathname])
  const isComplete = tip ? (completed[tip.id] ?? 0) >= tip.version : true

  useEffect(() => {
    if (!tip || !enabled || isComplete) {
      setPosition(null)
      return
    }

    const updatePosition = () => {
      if (document.querySelector(SUSPEND_SELECTOR)) {
        setPosition(null)
        return
      }

      const anchor = document.querySelector<HTMLElement>(
        `[data-guided-tip-anchor="${tip.anchor}"]`,
      )

      if (!anchor) {
        setPosition(null)
        return
      }

      const anchorRect = anchor.getBoundingClientRect()
      const calloutHeight = calloutRef.current?.getBoundingClientRect().height ?? 180
      setPosition({
        top: clamp(
          anchorRect.top,
          VIEWPORT_INSET,
          Math.max(VIEWPORT_INSET, window.innerHeight - calloutHeight - VIEWPORT_INSET),
        ),
        left: clamp(
          anchorRect.right + ANCHOR_GAP,
          VIEWPORT_INSET,
          Math.max(VIEWPORT_INSET, window.innerWidth - CALLOUT_WIDTH - VIEWPORT_INSET),
        ),
      })
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
      if (event.key === 'Escape' && !document.querySelector(SUSPEND_SELECTOR)) {
        complete(tip)
        setPosition(null)
      }
    }

    return () => {
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

  return (
    <aside
      ref={calloutRef}
      role="note"
      aria-label={`${tip.title} tip`}
      className="w-80 rounded-lg border bg-card p-4 text-card-foreground shadow-lg"
      style={{ position: 'fixed', top: position.top, left: position.left, zIndex: 50 }}
    >
      <p className="text-sm font-medium">{tip.title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{tip.body}</p>
      <div className="mt-3 flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={disable}>
          Don&apos;t show again
        </Button>
        <Button type="button" size="sm" onClick={dismiss}>
          Got it
        </Button>
      </div>
    </aside>
  )
}
