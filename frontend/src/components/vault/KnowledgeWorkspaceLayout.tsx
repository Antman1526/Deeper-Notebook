'use client'

import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { Columns2, Rows2, X } from 'lucide-react'

import {
  getKnowledgePanelId,
  getKnowledgeTabId,
  KnowledgeTabStrip,
} from '@/components/vault/KnowledgeTabStrip'
import { Button } from '@/components/ui/button'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type {
  KnowledgeLayoutNode,
  KnowledgePane,
  SplitDirection,
} from '@/lib/api/knowledge-workspace'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { cn } from '@/lib/utils'

interface KnowledgeWorkspaceLayoutProps {
  renderPane: (pane: KnowledgePane) => ReactNode
}

interface PaneActionProps {
  label: string
  disabled?: boolean
  icon: ReactNode
  onClick: () => void
}

function PaneAction({
  label,
  disabled,
  icon,
  onClick,
}: PaneActionProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
          className="size-8 text-muted-foreground hover:text-foreground"
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  )
}

interface PaneNodeProps {
  pane: KnowledgePane
  isActive: boolean
  canClose: boolean
  renderPane: KnowledgeWorkspaceLayoutProps['renderPane']
  activateTab: (paneId: string, tabId: string) => void
  closeTab: (paneId: string, tabId: string) => void
  setActivePane: (paneId: string) => void
  splitPane: (paneId: string, direction: SplitDirection) => string
  closePane: (paneId: string) => void
  registerPane: (paneId: string, element: HTMLElement | null) => void
}

function PaneNode({
  pane,
  isActive,
  canClose,
  renderPane,
  activateTab,
  closeTab,
  setActivePane,
  splitPane,
  closePane,
  registerPane,
}: PaneNodeProps) {
  const { t } = useTranslation()
  const activeTitle = pane.tabs.find((tab) => tab.id === pane.activeTabId)?.title
  const panelId = getKnowledgePanelId(pane.id)
  const activeTabDomId = pane.activeTabId
    ? getKnowledgeTabId(pane.id, pane.activeTabId)
    : undefined
  const paneLabel = `${t('knowledge.knowledgePane')} ${pane.id}${
    activeTitle ? `: ${activeTitle}` : ''
  }`

  return (
    <section
      ref={(element) => registerPane(pane.id, element)}
      aria-label={paneLabel}
      data-active={isActive ? 'true' : 'false'}
      tabIndex={-1}
      onClick={() => setActivePane(pane.id)}
      onFocus={() => setActivePane(pane.id)}
      className={cn(
        'flex h-full min-h-0 min-w-0 flex-col bg-background outline-none',
        isActive && 'ring-1 ring-inset ring-primary',
      )}
    >
      <div className="flex min-w-0 items-stretch">
        <KnowledgeTabStrip
          pane={pane}
          panelId={panelId}
          onActivateTab={activateTab}
          onCloseTab={closeTab}
        />
        <div
          role="toolbar"
          aria-label={paneLabel}
          onClick={(event) => {
            event.stopPropagation()
            if (event.target === event.currentTarget) {
              setActivePane(pane.id)
            }
          }}
          className="flex shrink-0 items-center border-b bg-muted/30 px-1"
        >
          <PaneAction
            label={t('knowledge.splitPaneRight')}
            icon={<Columns2 aria-hidden="true" className="size-4" />}
            onClick={() => splitPane(pane.id, 'horizontal')}
          />
          <PaneAction
            label={t('knowledge.splitPaneDown')}
            icon={<Rows2 aria-hidden="true" className="size-4" />}
            onClick={() => splitPane(pane.id, 'vertical')}
          />
          <PaneAction
            label={t('knowledge.closePane')}
            disabled={!canClose}
            icon={<X aria-hidden="true" className="size-4" />}
            onClick={() => closePane(pane.id)}
          />
        </div>
      </div>
      <div
        id={panelId}
        role="tabpanel"
        aria-labelledby={activeTabDomId}
        aria-label={activeTabDomId ? undefined : paneLabel}
        tabIndex={0}
        className="min-h-0 min-w-0 flex-1 overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        {renderPane(pane)}
      </div>
    </section>
  )
}

interface LayoutNodeProps extends Omit<PaneNodeProps, 'pane' | 'isActive'> {
  node: KnowledgeLayoutNode
  panes: Record<string, KnowledgePane>
  activePaneId: string
}

function LayoutNode({
  node,
  panes,
  activePaneId,
  ...paneProps
}: LayoutNodeProps) {
  const { t } = useTranslation()

  if (node.type === 'split') {
    const separatorLabel = node.direction === 'horizontal'
      ? t('knowledge.resizeHorizontalSplit')
      : t('knowledge.resizeVerticalSplit')

    return (
      <ResizablePanelGroup direction={node.direction}>
        <ResizablePanel defaultSize={50}>
          <LayoutNode
            node={node.first}
            panes={panes}
            activePaneId={activePaneId}
            {...paneProps}
          />
        </ResizablePanel>
        <ResizableHandle withHandle aria-label={separatorLabel} />
        <ResizablePanel defaultSize={50}>
          <LayoutNode
            node={node.second}
            panes={panes}
            activePaneId={activePaneId}
            {...paneProps}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    )
  }

  const pane = panes[node.paneId]
  if (!pane) return null

  return (
    <PaneNode
      pane={pane}
      isActive={activePaneId === pane.id}
      {...paneProps}
    />
  )
}

export function KnowledgeWorkspaceLayout({
  renderPane,
}: KnowledgeWorkspaceLayoutProps) {
  const { t } = useTranslation()
  const layout = useKnowledgeWorkspaceStore((state) => state.layout)
  const panes = useKnowledgeWorkspaceStore((state) => state.panes)
  const activePaneId = useKnowledgeWorkspaceStore((state) => state.activePaneId)
  const activateTab = useKnowledgeWorkspaceStore((state) => state.activateTab)
  const closeTab = useKnowledgeWorkspaceStore((state) => state.closeTab)
  const setActivePane = useKnowledgeWorkspaceStore((state) => state.setActivePane)
  const splitPane = useKnowledgeWorkspaceStore((state) => state.splitPane)
  const closePane = useKnowledgeWorkspaceStore((state) => state.closePane)
  const paneRefs = useRef<Record<string, HTMLElement | null>>({})
  const pendingPaneFocus = useRef(false)
  const canClose = Object.keys(panes).length > 1

  useLayoutEffect(() => {
    if (!pendingPaneFocus.current) return
    const activePane = paneRefs.current[activePaneId]
    if (!activePane) return
    pendingPaneFocus.current = false
    activePane.focus()
  }, [activePaneId, panes])

  const registerPane = (paneId: string, element: HTMLElement | null) => {
    paneRefs.current[paneId] = element
  }

  const closePaneWithFocus = (paneId: string) => {
    pendingPaneFocus.current = true
    closePane(paneId)
  }

  return (
    <section
      aria-label={t('knowledge.knowledgeWorkspace')}
      className="h-full min-h-0 min-w-0 overflow-hidden"
    >
      <LayoutNode
        node={layout}
        panes={panes}
        activePaneId={activePaneId}
        canClose={canClose}
        renderPane={renderPane}
        activateTab={activateTab}
        closeTab={closeTab}
        setActivePane={setActivePane}
        splitPane={splitPane}
        closePane={closePaneWithFocus}
        registerPane={registerPane}
      />
    </section>
  )
}
