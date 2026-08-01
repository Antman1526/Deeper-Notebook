'use client'

import { useMemo, useRef, useState, type KeyboardEvent } from 'react'

import type { KnowledgeTab } from '@/lib/api/knowledge-workspace'
import {
  RESEARCH_MODE_DESCRIPTORS,
  type ResearchMode,
} from '@/lib/knowledge/research-modes'
import { cn } from '@/lib/utils'

interface KnowledgeModeLauncherProps {
  activePaneId: string
  tabs: KnowledgeTab[]
  activeTabId?: string | null
  hasUnsavedOverlayDraft?: boolean
  availability?: Partial<Record<ResearchMode, { available: boolean; reason: string | null }>>
  onActivateTab: (paneId: string, tabId: string) => void
  onOpenMode: (mode: ResearchMode, paneId: string) => void
}

const MODES = Object.values(RESEARCH_MODE_DESCRIPTORS)

export function KnowledgeModeLauncher({
  activePaneId,
  tabs,
  activeTabId = null,
  hasUnsavedOverlayDraft = false,
  availability = {},
  onActivateTab,
  onOpenMode,
}: KnowledgeModeLauncherProps) {
  const [focusedIndex, setFocusedIndex] = useState(0)
  const modeRefs = useRef<Partial<Record<ResearchMode, HTMLButtonElement | null>>>({})
  const compatibleTabs = useMemo(() => new Map(
    tabs.filter((tab) => tab.mode && tab.target?.kind === RESEARCH_MODE_DESCRIPTORS[tab.mode].targetKind)
      .map((tab) => [tab.mode!, tab]),
  ), [tabs])

  const activateMode = (mode: ResearchMode) => {
    const existing = compatibleTabs.get(mode)
    if (existing) {
      onActivateTab(activePaneId, existing.id)
      return
    }
    onOpenMode(mode, activePaneId)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.altKey) {
      const descriptor = MODES.find((candidate) => candidate.shortcut === event.key)
      if (descriptor) {
        event.preventDefault()
        const availabilityForMode = availability[descriptor.id]
        if (availabilityForMode?.available !== false) activateMode(descriptor.id)
        return
      }
    }
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const next = event.key === 'ArrowRight'
      ? (focusedIndex + 1) % MODES.length
      : (focusedIndex - 1 + MODES.length) % MODES.length
    setFocusedIndex(next)
    modeRefs.current[MODES[next].id]?.focus()
  }

  return (
    <div role="toolbar" aria-label="Research modes" onKeyDown={onKeyDown} className="research-core-mode-surfaces flex flex-wrap gap-1">
      {MODES.map((descriptor, index) => {
        const modeAvailability = availability[descriptor.id]
        const isDisabled = modeAvailability?.available === false
        return (
          <button
            key={descriptor.id}
            ref={(element) => { modeRefs.current[descriptor.id] = element }}
            type="button"
            tabIndex={focusedIndex === index ? 0 : -1}
            disabled={isDisabled}
            title={modeAvailability?.reason ?? undefined}
            aria-label={`${descriptor.label} (Alt+${descriptor.shortcut})`}
            aria-pressed={tabs.find((tab) => tab.id === activeTabId)?.mode === descriptor.id}
            onFocus={() => setFocusedIndex(index)}
            onClick={() => activateMode(descriptor.id)}
            className={cn(
              'rounded-md border px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {descriptor.label}<span aria-hidden="true" className="ml-1 text-xs text-muted-foreground">Alt+{descriptor.shortcut}</span>
          </button>
        )
      })}
      {hasUnsavedOverlayDraft ? (
        <span className="sr-only" role="status">Unsaved Overlay draft remains open</span>
      ) : null}
    </div>
  )
}
