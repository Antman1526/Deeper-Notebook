'use client'

import { useMemo, useRef, useState } from 'react'
import { Minus, Plus, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { VaultCanvasDocument, VaultFile } from '@/lib/api/vault'

type CanvasNavigate = (
  vaultId: string,
  noteId: string,
  relativePathHint: string | undefined,
  titleHint: string | undefined,
  paneId: string | undefined,
  targetText: string | undefined,
  sourceAuthority: 'external-vault',
) => void

interface CanvasViewerProps {
  canvas?: VaultCanvasDocument
  isLoading?: boolean
  error?: unknown
  onRetry?: () => void
  vaultId?: string
  paneId?: string
  files?: VaultFile[]
  onNavigate?: CanvasNavigate
}

function nodeTitle(filePath: string, label: string | null): string {
  if (label?.trim()) return label
  return filePath.split('/').pop()?.replace(/\.md$/i, '') || filePath
}

export function CanvasViewer({
  canvas,
  isLoading = false,
  error,
  onRetry,
  vaultId,
  paneId,
  files = [],
  onNavigate,
}: CanvasViewerProps) {
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragOrigin = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null)
  const fileByPath = useMemo(() => new Map(
    files
      .filter((file) => file.vault_id === vaultId && /\.md$/i.test(file.relative_path))
      .map((file) => [file.relative_path, file]),
  ), [files, vaultId])
  const centers = useMemo(() => new Map(
    (canvas?.nodes ?? []).map((node) => [node.id, {
      x: node.x + node.width / 2,
      y: node.y + node.height / 2,
    }]),
  ), [canvas?.nodes])

  if (isLoading) return <div role="status" className="p-6 text-sm text-muted-foreground">Loading Canvas…</div>
  if (error || !canvas) {
    return (
      <div role="alert" className="m-4 rounded-md border border-destructive/30 p-4 text-sm">
        <p>The Canvas source is unavailable or no longer valid.</p>
        {onRetry && <Button type="button" className="mt-3" variant="outline" onClick={onRetry}>Retry Canvas</Button>}
      </div>
    )
  }

  const navigateFile = (relativePath: string, label: string | null) => {
    const file = fileByPath.get(relativePath)
    if (!file || !vaultId || !onNavigate) return
    const title = nodeTitle(relativePath, label)
    onNavigate(vaultId, file.note_id, relativePath, title, paneId, title, 'external-vault')
  }

  return (
    <section aria-label="Canvas viewer" className="flex h-full min-h-0 flex-col" tabIndex={0}>
      <div role="toolbar" aria-label="Canvas controls" className="flex items-center gap-2 border-b px-3 py-2">
        <Button type="button" size="icon" variant="ghost" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(0.5, value - 0.1))}>
          <Minus className="size-4" aria-hidden="true" />
        </Button>
        <span aria-live="polite" className="min-w-12 text-center text-xs text-muted-foreground">{Math.round(zoom * 100)}%</span>
        <Button type="button" size="icon" variant="ghost" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(2, value + 0.1))}>
          <Plus className="size-4" aria-hidden="true" />
        </Button>
        <Button type="button" size="icon" variant="ghost" aria-label="Reset Canvas view" onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }) }}>
          <RotateCcw className="size-4" aria-hidden="true" />
        </Button>
        <span className="ml-auto text-xs text-muted-foreground">Source {canvas.source_hash.slice(0, 12)}</span>
      </div>
      <div
        className="relative min-h-64 flex-1 overflow-hidden bg-muted/20"
        onPointerDown={(event) => {
          dragOrigin.current = { x: event.clientX, y: event.clientY, offsetX: offset.x, offsetY: offset.y }
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          const origin = dragOrigin.current
          if (!origin) return
          setOffset({ x: origin.offsetX + event.clientX - origin.x, y: origin.offsetY + event.clientY - origin.y })
        }}
        onPointerUp={() => { dragOrigin.current = null }}
      >
        <div className="absolute inset-0 origin-top-left" style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}>
          <svg aria-hidden="true" className="absolute inset-0 h-full w-full overflow-visible">
            {canvas.edges.map((edge) => {
              const from = centers.get(edge.from_node)
              const to = centers.get(edge.to_node)
              if (!from || !to) return null
              return <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="currentColor" className="text-muted-foreground" />
            })}
          </svg>
          <ul aria-label="Canvas nodes" className="relative m-0 list-none p-0">
            {canvas.nodes.map((node) => {
              const style = { left: node.x, top: node.y, width: node.width, height: node.height }
              const file = node.file_path ? fileByPath.get(node.file_path) : undefined
              const title = node.file_path ? nodeTitle(node.file_path, node.label) : node.label ?? node.text ?? node.type
              return (
                <li key={node.id} className="absolute rounded-md border bg-background p-2 text-sm shadow-sm" style={style}>
                  {node.type === 'file' && file
                    ? <Button type="button" variant="link" className="h-auto p-0" onClick={(event) => { event.stopPropagation(); navigateFile(node.file_path!, node.label) }}>{title}</Button>
                    : <span>{title}</span>}
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}
