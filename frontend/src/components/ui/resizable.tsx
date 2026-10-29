'use client'

// v0.8.85 — shadcn "resizable" primitive (improvement roadmap, Batch 3),
// wrapping react-resizable-panels. Used by the notebook workspace for
// draggable, width-remembered sources | notes | chat panes.
import { GripVertical } from 'lucide-react'
import * as ResizablePrimitive from 'react-resizable-panels'

import { cn } from '@/lib/utils'

function ResizablePanelGroup({
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.PanelGroup>) {
  return (
    <ResizablePrimitive.PanelGroup
      className={cn(
        'flex h-full w-full data-[panel-group-direction=vertical]:flex-col',
        className
      )}
      {...props}
    />
  )
}

const ResizablePanel = ResizablePrimitive.Panel

function ResizableHandle({
  withHandle,
  onReset,
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.PanelResizeHandle> & {
  withHandle?: boolean
  /** v0.8.130 — double-click puts the columns back to their default widths. */
  onReset?: () => void
}) {
  return (
    <ResizablePrimitive.PanelResizeHandle
      onDoubleClick={onReset}
      className={cn(
        'group relative flex w-px items-center justify-center bg-border/80 transition-colors duration-200',
        'after:absolute after:inset-y-0 after:left-1/2 after:w-3.5 after:-translate-x-1/2',
        // v0.8.130 — the teal glows were the old brand hue hard-coded into every theme.
        'data-[resize-handle-state=hover]:bg-primary/70',
        'data-[resize-handle-state=drag]:bg-primary',
        'data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full',
        'data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-3.5 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:-translate-y-1/2 data-[panel-group-direction=vertical]:after:translate-x-0',
        className
      )}
      {...props}
    >
      {withHandle && (
        // v0.8.130 — the grip answers the handle's own hover and drag states, which
        // cover its wider hit area: it barely changed unless the pointer sat exactly
        // on the 1px line, and gave no sign at all while dragging.
        <div
          data-dn-resize-grip=""
          className={cn(
            'z-10 flex h-8 w-4 items-center justify-center rounded-full border border-border bg-card shadow-xs transition-[background-color,border-color,color] duration-200',
            'group-hover:border-primary/50 group-data-[resize-handle-state=hover]:border-primary/60',
            'group-data-[resize-handle-state=drag]:border-primary group-data-[resize-handle-state=drag]:bg-primary',
          )}
        >
          <GripVertical
            className={cn(
              'h-3 w-3 text-muted-foreground transition-colors',
              'group-hover:text-primary group-data-[resize-handle-state=hover]:text-primary',
              'group-data-[resize-handle-state=drag]:text-primary-foreground',
            )}
          />
        </div>
      )}
    </ResizablePrimitive.PanelResizeHandle>
  )
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle }
