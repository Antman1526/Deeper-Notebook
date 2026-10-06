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
import { KNOWLEDGE_TARGET_STATE_KEYS, enumLabel } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'

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
  const { t } = useTranslation()
  const unavailableTabs = plan
    ? Object.values(plan.panes).flatMap((pane) => pane.tabs)
      .filter((tab) => tab.targetState !== 'available' || !tab.targetDocument)
    : []

  return (
    <Dialog open={Boolean(plan)} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-lg" showCloseButton={!applying}>
        <DialogHeader>
          <DialogTitle>{t('knowledge.workspaceRestoreDialog.title')}</DialogTitle>
          <DialogDescription>
            {t('knowledge.workspaceRestoreDialog.description')}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-64 space-y-2 overflow-y-auto" aria-label={t('knowledge.workspaceRestoreDialog.targets')}>
          {unavailableTabs.map((tab) => (
            <div key={tab.id} className="flex items-center justify-between gap-3 rounded-md border p-2 text-sm">
              <span className="min-w-0 truncate">{tab.displayLabel}</span>
              <span className="shrink-0 text-muted-foreground">{enumLabel(t, KNOWLEDGE_TARGET_STATE_KEYS, tab.targetState)}</span>
            </div>
          ))}
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={applying}>{t('common.cancel')}</Button>
          <Button type="button" onClick={onOpenAvailable} disabled={applying}>
            {applying ? t('knowledge.workspaceRestoreDialog.opening') : t('knowledge.navigation.openAvailable')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
