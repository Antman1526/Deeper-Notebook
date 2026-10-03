'use client'

import { useMemo, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react'
import { ChevronDown, ChevronRight, Download, MessageCircle, Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import apiClient from '@/lib/api/client'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface MindMapArtifactNode {
  /** Stable child-index path; e.g. root=0, first child=0/0. */
  id: string
  label: string
  relationship: string
  citations: string[]
  children: MindMapArtifactNode[]
}

export interface MindMapChatContext {
  artifact_id: string
  notebook_id: string
  node_path: string
  label: string
  relationship: string
  citations: string[]
  source_ids: string[]
  prompt_context: string
}

type BranchArtifactType = 'report' | 'study_guide' | 'course_pack' | 'briefing' | 'faq' | 'flashcards' | 'quiz' | 'data_table' | 'timeline' | 'infographic' | 'slide_deck' | 'podcast_outline' | 'research_run'

const BRANCH_ARTIFACTS: Array<{ value: BranchArtifactType; labelKey: string }> = [
  { value: 'report', labelKey: 'artifacts.mindMapArtifactViewer.type.report' },
  { value: 'study_guide', labelKey: 'artifacts.mindMapArtifactViewer.type.studyGuide' },
  { value: 'course_pack', labelKey: 'artifacts.mindMapArtifactViewer.type.coursePack' },
  { value: 'briefing', labelKey: 'artifacts.mindMapArtifactViewer.type.briefing' },
  { value: 'faq', labelKey: 'artifacts.mindMapArtifactViewer.type.faq' },
  { value: 'flashcards', labelKey: 'artifacts.mindMapArtifactViewer.type.flashcards' },
  { value: 'quiz', labelKey: 'artifacts.mindMapArtifactViewer.type.quiz' },
  { value: 'data_table', labelKey: 'artifacts.mindMapArtifactViewer.type.dataTable' },
  { value: 'timeline', labelKey: 'artifacts.mindMapArtifactViewer.type.timeline' },
  { value: 'infographic', labelKey: 'artifacts.mindMapArtifactViewer.type.infographic' },
  { value: 'slide_deck', labelKey: 'artifacts.mindMapArtifactViewer.type.slideDeck' },
  { value: 'podcast_outline', labelKey: 'artifacts.mindMapArtifactViewer.type.podcastOutline' },
  { value: 'research_run', labelKey: 'artifacts.mindMapArtifactViewer.type.researchRun' },
]

function flattenVisible(nodes: MindMapArtifactNode[], collapsed: Set<string>): MindMapArtifactNode[] {
  const visible: MindMapArtifactNode[] = []
  const visit = (node: MindMapArtifactNode) => {
    visible.push(node)
    if (!collapsed.has(node.id)) node.children.forEach(visit)
  }
  nodes.forEach(visit)
  return visible
}

function toFlowGraph(nodes: MindMapArtifactNode[], collapsed: Set<string>): { nodes: Node[]; edges: Edge[] } {
  const visible = flattenVisible(nodes, collapsed)
  const visibleIds = new Set(visible.map((node) => node.id))
  const flowNodes = visible.map((node, row) => {
    const depth = node.id.split('/').length - 1
    return {
      id: node.id,
      position: { x: depth * 270, y: row * 104 },
      data: { label: node.label },
      // v0.8.130 — node colours from theme tokens (UI audit Phase 1); React Flow
      // applies this as an inline style, so CSS variables resolve per theme.
      style: {
        background: 'var(--card)', border: '1px solid var(--muted-foreground)', borderRadius: 6,
        color: 'var(--card-foreground)', fontSize: 13, fontWeight: 600, maxWidth: 220,
        padding: '10px 14px', textAlign: 'center' as const,
      },
    }
  })
  const edges = flowNodes.flatMap((node) => {
    const separator = node.id.lastIndexOf('/')
    const parentId = separator === -1 ? null : node.id.slice(0, separator)
    return parentId && visibleIds.has(parentId)
      ? [{ id: `edge-${parentId}-${node.id}`, source: parentId, target: node.id, style: { stroke: 'var(--muted-foreground)', strokeWidth: 1.5 } }]
      : []
  })
  return { nodes: flowNodes, edges }
}

export function MindMapArtifactViewer({
  nodes,
  artifactId,
  notebookId,
  onContextReady,
  onArtifactCreated,
}: {
  nodes: MindMapArtifactNode[]
  artifactId?: string
  notebookId?: string
  onContextReady?: (context: MindMapChatContext) => void
  onArtifactCreated?: (artifactId: string) => void
}) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [selectedId, setSelectedId] = useState(nodes[0]?.id ?? '')
  const [targetType, setTargetType] = useState<BranchArtifactType>('study_guide')
  const [isRequesting, setIsRequesting] = useState(false)
  const visible = useMemo(() => flattenVisible(nodes, collapsed), [nodes, collapsed])
  const { nodes: flowNodes, edges } = useMemo(() => toFlowGraph(nodes, collapsed), [nodes, collapsed])
  const selected = visible.find((node) => node.id === selectedId) ?? visible[0]
  const selectedHasChildren = Boolean(selected?.children.length)
  const actionsAvailable = Boolean(artifactId && notebookId && selected)

  const toggleSelected = () => {
    if (!selectedHasChildren || !selected) return
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(selected.id)) next.delete(selected.id)
      else next.add(selected.id)
      return next
    })
  }

  const selectWithKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (visible.length === 0) return
    const currentIndex = Math.max(0, visible.findIndex((node) => node.id === selected?.id))
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      event.preventDefault()
      setSelectedId(visible[Math.min(currentIndex + 1, visible.length - 1)].id)
    } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault()
      setSelectedId(visible[Math.max(currentIndex - 1, 0)].id)
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleSelected()
    }
  }

  const onNodeClick = (_event: MouseEvent, node: Node) => setSelectedId(node.id)

  const requestContext = async () => {
    if (!artifactId || !notebookId || !selected) return
    setIsRequesting(true)
    try {
      const response = await apiClient.post<MindMapChatContext>(
        `/studio/artifacts/${encodeURIComponent(artifactId)}/mind-map/branches/${encodeURIComponent(selected.id)}/context`,
        { notebook_id: notebookId },
      )
      const context = response.data
      onContextReady?.(context)
      window.dispatchEvent(new CustomEvent<MindMapChatContext>('onp:mind-map-context', { detail: context }))
    } finally {
      setIsRequesting(false)
    }
  }

  const createFromBranch = async () => {
    if (!artifactId || !notebookId || !selected) return
    setIsRequesting(true)
    try {
      const response = await apiClient.post<{ id: string }>(
        `/studio/artifacts/${encodeURIComponent(artifactId)}/mind-map/branches/${encodeURIComponent(selected.id)}/artifacts`,
        { notebook_id: notebookId, artifact_type: targetType },
      )
      onArtifactCreated?.(response.data.id)
    } finally {
      setIsRequesting(false)
    }
  }

  if (nodes.length === 0) return null

  return (
    <section className="space-y-3" aria-label={t('artifacts.mindMapArtifactViewer.regionLabel')}>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div
          tabIndex={0}
          onKeyDown={selectWithKeyboard}
          className="h-[28rem] min-h-[18rem] rounded-md border bg-muted/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t('artifacts.mindMapArtifactViewer.canvasLabel')}
        >
          <ReactFlow
            nodes={flowNodes}
            edges={edges}
            onNodeClick={onNodeClick}
            fitView
            minZoom={0.2}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>

        <aside className="space-y-3 rounded-md border bg-background p-3" aria-live="polite">
          <div>
            <div className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{t('artifacts.mindMapArtifactViewer.selectedTopic')}</div>
            <div className="mt-1 text-sm font-semibold">{selected?.label}</div>
            {selected?.relationship && <div className="mt-1 text-xs text-muted-foreground">{selected.relationship}</div>}
          </div>
          {selected?.citations.length ? (
            <div className="flex flex-wrap gap-1">
              {selected.citations.map((citation) => <Badge key={citation} variant="outline">{citation}</Badge>)}
            </div>
          ) : <div className="text-xs text-muted-foreground">{t('artifacts.mindMapArtifactViewer.noCitations')}</div>}
          {selectedHasChildren && (
            <Button type="button" variant="outline" className="w-full justify-start" onClick={toggleSelected}>
              {collapsed.has(selected?.id ?? '') ? <ChevronRight className="mr-2 h-4 w-4" /> : <ChevronDown className="mr-2 h-4 w-4" />}
              {collapsed.has(selected?.id ?? '') ? t('artifacts.mindMapArtifactViewer.expandBranch') : t('artifacts.mindMapArtifactViewer.collapseBranch')}
            </Button>
          )}
          {actionsAvailable ? (
            <>
              <Button type="button" className="w-full justify-start" onClick={() => void requestContext()} disabled={isRequesting}>
                <MessageCircle className="mr-2 h-4 w-4" /> {t('artifacts.mindMapArtifactViewer.askAboutTopic')}
              </Button>
              <div className="space-y-2 border-t pt-3">
                <label className="text-xs font-medium" htmlFor="mind-map-branch-artifact">{t('artifacts.mindMapArtifactViewer.createFromBranch')}</label>
                <select id="mind-map-branch-artifact" value={targetType} onChange={(event) => setTargetType(event.target.value as BranchArtifactType)} className="h-9 w-full rounded-md border bg-background px-2 text-sm">
                  {BRANCH_ARTIFACTS.map((artifact) => <option key={artifact.value} value={artifact.value}>{t(artifact.labelKey)}</option>)}
                </select>
                <Button type="button" variant="outline" className="w-full justify-start" onClick={() => void createFromBranch()} disabled={isRequesting}>
                  <Sparkles className="mr-2 h-4 w-4" /> {t('artifacts.mindMapArtifactViewer.createType', { type: t(BRANCH_ARTIFACTS.find((item) => item.value === targetType)?.labelKey ?? '') })}
                </Button>
              </div>
              <a className="inline-flex h-9 w-full items-center justify-start rounded-md px-3 text-sm hover:bg-muted" href={`/api/studio/artifacts/${encodeURIComponent(artifactId ?? '')}/mind-map.svg?notebook_id=${encodeURIComponent(notebookId ?? '')}`}>
                <Download className="mr-2 h-4 w-4" /> {t('artifacts.mindMapArtifactViewer.downloadSvg')}
              </a>
            </>
          ) : <div className="text-xs text-muted-foreground">{t('artifacts.mindMapArtifactViewer.branchActionsUnavailable')}</div>}
        </aside>
      </div>
    </section>
  )
}
