'use client'

import { useEffect, useRef, useState } from 'react'

import type { KnowledgeNavigate } from './KnowledgePaneContent'
import { KnowledgeLinksInspector } from './KnowledgeLinksInspector'

type IntelligencePanel = 'evidence' | 'connections' | 'properties' | 'production'

interface KnowledgeIntelligenceRailProps {
  activeContext: { evidence: string; properties: string; production: string }
  onNavigate: KnowledgeNavigate
  initialPanel?: IntelligencePanel
  drawerId?: string
  drawerLabel?: string
  drawerOpen?: boolean
  drawerCloseLabel?: string
  onCloseDrawer?: () => void
}

const PANELS: Array<{ id: IntelligencePanel; label: string }> = [
  { id: 'evidence', label: 'Evidence' },
  { id: 'connections', label: 'Connections' },
  { id: 'properties', label: 'Properties' },
  { id: 'production', label: 'Production' },
]

export function KnowledgeIntelligenceRail({
  activeContext,
  onNavigate,
  initialPanel = 'evidence',
  drawerId,
  drawerLabel = 'Research intelligence',
  drawerOpen = true,
  drawerCloseLabel,
  onCloseDrawer,
}: KnowledgeIntelligenceRailProps) {
  const [panel, setPanel] = useState<IntelligencePanel>(initialPanel)
  const [collapsed, setCollapsed] = useState(false)
  const toggleRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (collapsed) toggleRef.current?.focus()
  }, [collapsed])

  return (
    <aside
      id={drawerId}
      aria-label={drawerLabel}
      aria-hidden={!drawerOpen}
      data-drawer-open={drawerOpen ? 'true' : 'false'}
      className="research-core-intelligence-drawer min-w-0 border-l"
    >
      <div className="flex items-center justify-between gap-2 border-b p-2">
        <span className="text-sm font-medium">Intelligence</span>
        <div className="flex items-center gap-1">
          {onCloseDrawer && drawerCloseLabel ? (
            <button
              type="button"
              aria-label={drawerCloseLabel}
              onClick={onCloseDrawer}
              className="research-core-drawer-close rounded px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {drawerCloseLabel}
            </button>
          ) : null}
          <button
            ref={toggleRef}
            type="button"
            aria-expanded={!collapsed}
            aria-label={collapsed ? 'Expand intelligence rail' : 'Collapse intelligence rail'}
            onClick={() => setCollapsed((value) => !value)}
            className="rounded px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {collapsed ? 'Expand' : 'Collapse'}
          </button>
        </div>
      </div>
      {!collapsed ? (
        <div className="p-3">
          <nav aria-label="Intelligence panels" className="mb-3 flex flex-wrap gap-1">
            {PANELS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={panel === item.id}
                onClick={() => setPanel(item.id)}
                className="rounded border px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {item.label}
              </button>
            ))}
          </nav>
          {panel === 'evidence' ? <p>{activeContext.evidence}</p> : null}
          {panel === 'connections' ? <KnowledgeLinksInspector embedded onNavigate={onNavigate} /> : null}
          {panel === 'properties' ? <p>{activeContext.properties}</p> : null}
          {panel === 'production' ? <p>{activeContext.production}</p> : null}
        </div>
      ) : null}
    </aside>
  )
}
