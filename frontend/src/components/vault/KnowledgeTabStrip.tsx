'use client'

import { useLayoutEffect, useRef, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { KnowledgePane } from '@/lib/api/knowledge-workspace'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface KnowledgeTabStripProps {
  pane: KnowledgePane
  panelId?: string
  onActivateTab: (paneId: string, tabId: string) => void
  onCloseTab: (paneId: string, tabId: string) => void
  onRequestFocusFallback?: () => void
}

export function getKnowledgePanelId(paneId: string): string {
  return `knowledge-panel-${encodeURIComponent(paneId)}`
}

function encodeDomIdPart(value: string): string {
  const encoded = encodeURIComponent(value)
  return `${encoded.length}:${encoded}`
}

export function getKnowledgeTabId(paneId: string, tabId: string): string {
  return `knowledge-tab-${encodeDomIdPart(paneId)}-${encodeDomIdPart(tabId)}`
}

export function getEffectiveKnowledgeTabId(pane: KnowledgePane): string | null {
  return pane.activeTabId ?? pane.tabs[0]?.id ?? null
}

export function KnowledgeTabStrip({
  pane,
  panelId = getKnowledgePanelId(pane.id),
  onActivateTab,
  onCloseTab,
  onRequestFocusFallback,
}: KnowledgeTabStripProps) {
  const { t } = useTranslation()
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const pendingFocusTabId = useRef<string | null>(null)
  const pendingFallbackFocus = useRef(false)
  const effectiveActiveTabId = getEffectiveKnowledgeTabId(pane)

  useLayoutEffect(() => {
    const targetTabId = pendingFocusTabId.current
    if (targetTabId && effectiveActiveTabId === targetTabId) {
      const targetTab = tabRefs.current[targetTabId]
      if (!targetTab) return
      pendingFocusTabId.current = null
      targetTab.focus()
      return
    }

    if (pendingFallbackFocus.current && pane.tabs.length === 0) {
      pendingFallbackFocus.current = false
      onRequestFocusFallback?.()
    }
  }, [effectiveActiveTabId, onRequestFocusFallback, pane.tabs])

  const closeTab = (tabId: string) => {
    const closedIndex = pane.tabs.findIndex((tab) => tab.id === tabId)
    const remainingTabs = pane.tabs.filter((tab) => tab.id !== tabId)
    const focusTargetTabId = effectiveActiveTabId === tabId
      ? remainingTabs[closedIndex]?.id
        ?? remainingTabs[closedIndex - 1]?.id
        ?? null
      : effectiveActiveTabId
    pendingFocusTabId.current = focusTargetTabId
    pendingFallbackFocus.current = focusTargetTabId === null
    onCloseTab(pane.id, tabId)
  }

  const moveSelection = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    if (pane.tabs.length === 0) return

    let targetIndex: number | null = null
    switch (event.key) {
      case 'ArrowRight':
        targetIndex = (currentIndex + 1) % pane.tabs.length
        break
      case 'ArrowLeft':
        targetIndex = (currentIndex - 1 + pane.tabs.length) % pane.tabs.length
        break
      case 'Home':
        targetIndex = 0
        break
      case 'End':
        targetIndex = pane.tabs.length - 1
        break
      default:
        return
    }

    event.preventDefault()
    const targetTab = pane.tabs[targetIndex]
    onActivateTab(pane.id, targetTab.id)
    tabRefs.current[targetTab.id]?.focus()
  }

  return (
    <div
      role="tablist"
      aria-label={t('knowledge.openTabs')}
      aria-orientation="horizontal"
      className="flex min-w-0 flex-1 items-stretch overflow-x-auto border-b bg-muted/30"
    >
      {pane.tabs.map((tab, index) => {
        const isActive = tab.id === effectiveActiveTabId
        const closeLabel = t('knowledge.closeTab', { title: tab.title })

        return (
          <div
            key={tab.id}
            role="presentation"
            className={cn(
              'group flex min-w-0 max-w-64 shrink-0 items-center border-r',
              isActive && 'bg-background text-foreground',
            )}
          >
            <button
              ref={(element) => {
                tabRefs.current[tab.id] = element
              }}
              id={getKnowledgeTabId(pane.id, tab.id)}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={panelId}
              tabIndex={isActive ? 0 : -1}
              title={tab.relativePath}
              onClick={() => onActivateTab(pane.id, tab.id)}
              onKeyDown={(event) => moveSelection(event, index)}
              className={cn(
                'relative min-w-0 flex-1 truncate px-3 py-2 text-left text-sm',
                'outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                'after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:bg-transparent',
                isActive
                  ? 'font-medium after:bg-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )}
            >
              {tab.title}
            </button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={closeLabel}
                  onClick={() => closeTab(tab.id)}
                  className="mr-1 size-7 shrink-0 text-muted-foreground hover:text-foreground"
                >
                  <X aria-hidden="true" className="size-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">{closeLabel}</TooltipContent>
            </Tooltip>
          </div>
        )
      })}
    </div>
  )
}
