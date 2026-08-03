'use client'

import { useEffect, useMemo, type MouseEvent } from 'react'
import { Background, Controls, ReactFlow, type Edge, type Node, type Viewport } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { VaultGraph as VaultGraphData, VaultLink } from '@/lib/api/vault'
import { TurnIntoPodcastAction } from '@/components/podcasts/TurnIntoPodcastAction'
import { useTranslation } from '@/lib/hooks/use-translation'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'
import './vault.css'

export function VaultGraph({ graph, unresolved, onNavigate, viewport, onMoveEnd, rootDocumentId, spaceIds = [], relationKinds = [], onBookmarkContext }: {
  graph?: VaultGraphData
  unresolved: VaultLink[]
  onNavigate: (noteId: string) => void
  viewport?: Viewport
  onMoveEnd?: (viewport: Viewport) => void
  rootDocumentId?: string | null
  spaceIds?: string[]
  relationKinds?: string[]
  onBookmarkContext?: (context: { rootDocumentId: string; spaceIds: string[]; relationKinds: string[]; viewport: Viewport }) => void
}) {
  const { t } = useTranslation()
  const openPodcastReview = usePodcastStudioStore((state) => state.open)
  const { nodes, edges } = useMemo(() => {
    const source = graph?.nodes ?? []
    const flowNodes: Node[] = source.map((node, index) => ({ id: node.id, data: { label: node.title || node.id }, position: { x: (index % 3) * 240, y: Math.floor(index / 3) * 130 }, draggable: false, className: `vault-node--${node.source_format || 'markdown'}` }))
    const allowedRelations = relationKinds.length ? new Set(relationKinds) : null
    const flowEdges: Edge[] = (graph?.edges ?? []).filter((edge) => !allowedRelations || allowedRelations.has(edge.kind || 'related')).map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, className: 'vault-edge--resolved' }))
    unresolved.forEach((link, index) => {
      const id = `unresolved:${link.id}`
      flowNodes.push({ id, data: { label: link.target_text }, position: { x: 720, y: index * 130 }, draggable: false, selectable: false, className: 'vault-node--unresolved' })
      flowEdges.push({ id: `unresolved-edge:${link.id}`, source: link.source_note_id, target: id, className: 'vault-edge--unresolved' })
    })
    return { nodes: flowNodes, edges: flowEdges }
  }, [graph, relationKinds, unresolved])
  const liveRelationKinds = useMemo(() => relationKinds.length
    ? relationKinds
    : [...new Set((graph?.edges ?? []).map((edge) => edge.kind || 'related'))].filter((kind) => /^[A-Za-z0-9_.:-]{1,64}$/.test(kind)), [graph, relationKinds])
  useEffect(() => {
    if (!rootDocumentId || !onBookmarkContext || !viewport) return
    onBookmarkContext({ rootDocumentId, spaceIds, relationKinds: liveRelationKinds, viewport })
  }, [liveRelationKinds, onBookmarkContext, rootDocumentId, spaceIds, viewport])
  if (!nodes.length) return <p className="flex h-full items-center justify-center rounded-md border border-dashed p-6 text-sm text-muted-foreground">{t('knowledge.noGraphLinks')}</p>
  const podcastDocumentIds = [...new Set(
    (graph?.nodes ?? [])
      .map((node) => node.knowledge_document_id)
      .filter((documentId): documentId is string => Boolean(documentId)),
  )].slice(0, 128)
  return <section className="space-y-3" aria-label={t('knowledge.localGraph')}>
    <TurnIntoPodcastAction
      selection={podcastDocumentIds.length > 0
        ? { kind: 'graph_selection', documentIds: podcastDocumentIds }
        : undefined}
      destination="quick"
      label="Turn graph into podcast"
      disabledReason={podcastDocumentIds.length > 0
        ? undefined
        : 'This graph has no unified document selection yet.'}
      onOpen={openPodcastReview}
    />
    <div className="vault-flow h-[480px] overflow-hidden rounded-md border"><ReactFlow nodes={nodes} edges={edges} viewport={viewport} fitView={!viewport} nodesConnectable={false} nodesDraggable={false} onConnect={() => undefined} onMoveEnd={(_event, nextViewport) => onMoveEnd?.(nextViewport)} onNodeClick={(_event: MouseEvent, node) => { if (!node.id.startsWith('unresolved:')) onNavigate(node.id) }} proOptions={{ hideAttribution: true }}><Background /><Controls showInteractive={false} /></ReactFlow></div>
  </section>
}
