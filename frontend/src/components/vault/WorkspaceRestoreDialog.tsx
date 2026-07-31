'use client'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { WorkspaceRestorePlan } from '@/lib/api/knowledge-navigation'

interface WorkspaceRestoreDialogProps {
  plan: WorkspaceRestorePlan | null
  onOpenAvailable: () => void
  onCancel: () => void
  applying?: boolean
  error?: string | null
}

export function WorkspaceRestoreDialog({
  plan,
  onOpenAvailable,
  onCancel,
  applying = false,
  error = null,
}: WorkspaceRestoreDialogProps) {
  const unavailableTabs = plan
    ? Object.values(plan.panes).flatMap((pane) => pane.tabs)
      .filter((tab) => tab.targetState !== 'available' || !tab.targetDocument)
    : []

  return (
    <Dialog open={Boolean(plan)} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={!applying}>
        <DialogHeader>
          <DialogTitle>Open workspace with unavailable targets</DialogTitle>
          <DialogDescription>
            The current session will not change until you choose Open available.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-64 space-y-2 overflow-y-auto" aria-label="Unavailable workspace targets">
          {unavailableTabs.map((tab) => (
            <div key={tab.id} className="flex items-center justify-between gap-3 rounded-md border p-2 text-sm">
              <span className="min-w-0 truncate">{tab.displayLabel}</span>
              <span className="shrink-0 text-muted-foreground">{tab.targetState}</span>
            </div>
          ))}
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={applying}>Cancel</Button>
          <Button type="button" onClick={onOpenAvailable} disabled={applying}>
            {applying ? 'Opening…' : 'Open available'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
