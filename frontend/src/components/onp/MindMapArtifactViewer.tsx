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

const BRANCH_ARTIFACTS: Array<{ value: BranchArtifactType; label: string }> = [
  { value: 'report', label: 'Report' },
  { value: 'study_guide', label: 'Study guide' },
  { value: 'course_pack', label: 'Course Pack' },
  { value: 'briefing', label: 'Briefing' },
  { value: 'faq', label: 'FAQ' },
  { value: 'flashcards', label: 'Flashcards' },
  { value: 'quiz', label: 'Quiz' },
  { value: 'data_table', label: 'Data table' },
  { value: 'timeline', label: 'Timeline' },
  { value: 'infographic', label: 'Infographic' },
  { value: 'slide_deck', label: 'Slide deck' },
  { value: 'podcast_outline', label: 'Podcast outline' },
  { value: 'research_run', label: 'Research run' },
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
      style: {
        background: '#f8fafc', border: '1px solid #475569', borderRadius: 6,
        color: '#0f172a', fontSize: 13, fontWeight: 600, maxWidth: 220,
        padding: '10px 14px', textAlign: 'center' as const,
      },
    }
  })
  const edges = flowNodes.flatMap((node) => {
    const separator = node.id.lastIndexOf('/')
    const parentId = separator === -1 ? null : node.id.slice(0, separator)
    return parentId && visibleIds.has(parentId)
      ? [{ id: `edge-${parentId}-${node.id}`, source: parentId, target: node.id, style: { stroke: '#94a3b8', strokeWidth: 1.5 } }]
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
    <section className="space-y-3" aria-label="Interactive mind map">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div
          tabIndex={0}
          onKeyDown={selectWithKeyboard}
          className="h-[28rem] min-h-[18rem] rounded-md border bg-muted/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Mind map canvas. Use arrow keys to move between nodes and Enter to expand or collapse the selected branch."
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
            <div className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Selected topic</div>
            <div className="mt-1 text-sm font-semibold">{selected?.label}</div>
            {selected?.relationship && <div className="mt-1 text-xs text-muted-foreground">{selected.relationship}</div>}
          </div>
          {selected?.citations.length ? (
            <div className="flex flex-wrap gap-1">
              {selected.citations.map((citation) => <Badge key={citation} variant="outline">{citation}</Badge>)}
            </div>
          ) : <div className="text-xs text-muted-foreground">No citations on this branch.</div>}
          {selectedHasChildren && (
            <Button type="button" variant="outline" className="w-full justify-start" onClick={toggleSelected}>
              {collapsed.has(selected?.id ?? '') ? <ChevronRight className="mr-2 h-4 w-4" /> : <ChevronDown className="mr-2 h-4 w-4" />}
              {collapsed.has(selected?.id ?? '') ? 'Expand branch' : 'Collapse branch'}
            </Button>
          )}
          {actionsAvailable ? (
            <>
              <Button type="button" className="w-full justify-start" onClick={() => void requestContext()} disabled={isRequesting}>
                <MessageCircle className="mr-2 h-4 w-4" /> Ask about this topic
              </Button>
              <div className="space-y-2 border-t pt-3">
                <label className="text-xs font-medium" htmlFor="mind-map-branch-artifact">Create from branch</label>
                <select id="mind-map-branch-artifact" value={targetType} onChange={(event) => setTargetType(event.target.value as BranchArtifactType)} className="h-9 w-full rounded-md border bg-background px-2 text-sm">
                  {BRANCH_ARTIFACTS.map((artifact) => <option key={artifact.value} value={artifact.value}>{artifact.label}</option>)}
                </select>
                <Button type="button" variant="outline" className="w-full justify-start" onClick={() => void createFromBranch()} disabled={isRequesting}>
                  <Sparkles className="mr-2 h-4 w-4" /> Create {BRANCH_ARTIFACTS.find((item) => item.value === targetType)?.label}
                </Button>
              </div>
              <a className="inline-flex h-9 w-full items-center justify-start rounded-md px-3 text-sm hover:bg-muted" href={`/api/studio/artifacts/${encodeURIComponent(artifactId ?? '')}/mind-map.svg?notebook_id=${encodeURIComponent(notebookId ?? '')}`}>
                <Download className="mr-2 h-4 w-4" /> Download SVG
              </a>
            </>
          ) : <div className="text-xs text-muted-foreground">Branch actions become available when this view is opened with its artifact context.</div>}
        </aside>
      </div>
    </section>
  )
}
