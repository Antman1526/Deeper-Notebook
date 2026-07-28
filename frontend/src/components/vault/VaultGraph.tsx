'use client'

import { useMemo, type MouseEvent } from 'react'
import { Background, Controls, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import type { VaultGraph as VaultGraphData, VaultLink } from '@/lib/api/vault'
import './vault.css'

export function VaultGraph({ graph, unresolved, onNavigate }: { graph?: VaultGraphData; unresolved: VaultLink[]; onNavigate: (noteId: string) => void }) {
  const { nodes, edges } = useMemo(() => {
    const source = graph?.nodes ?? []
    const flowNodes: Node[] = source.map((node, index) => ({ id: node.id, data: { label: node.title || node.id }, position: { x: (index % 3) * 240, y: Math.floor(index / 3) * 130 }, draggable: false, className: `vault-node--${node.source_format || 'markdown'}` }))
    const flowEdges: Edge[] = (graph?.edges ?? []).map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, className: 'vault-edge--resolved' }))
    unresolved.forEach((link, index) => {
      const id = `unresolved:${link.id}`
      flowNodes.push({ id, data: { label: link.target_text }, position: { x: 720, y: index * 130 }, draggable: false, selectable: false, className: 'vault-node--unresolved' })
      flowEdges.push({ id: `unresolved-edge:${link.id}`, source: link.source_note_id, target: id, className: 'vault-edge--unresolved' })
    })
    return { nodes: flowNodes, edges: flowEdges }
  }, [graph, unresolved])
  if (!nodes.length) return <p className="flex h-full items-center justify-center rounded-md border border-dashed p-6 text-sm text-muted-foreground">No note links to map yet.</p>
  return <div className="vault-flow h-[480px] overflow-hidden rounded-md border" aria-label="Local note link graph"><ReactFlow nodes={nodes} edges={edges} fitView nodesConnectable={false} nodesDraggable={false} onConnect={() => undefined} onNodeClick={(_event: MouseEvent, node) => { if (!node.id.startsWith('unresolved:')) onNavigate(node.id) }} proOptions={{ hideAttribution: true }}><Background /><Controls showInteractive={false} /></ReactFlow></div>
}
