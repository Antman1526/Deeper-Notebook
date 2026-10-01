// v0.7.119 — Bulk-vectorize button + confirm dialog for the Sources
// column. Submits one embed_source command per notebook source via
// POST /notebooks/{id}/vectorize_sources. With `only_missing=true`
// (default) re-running is a safe no-op; toggling it off forces full
// re-embedding (useful after switching embedding models).
'use client'

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Sparkles } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useVectorizeNotebookSources } from '@/lib/hooks/use-notebooks'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'

interface BulkVectorizeButtonProps {
  notebookId: string
  // v0.8.130 — Phase 2b: controlled mode so a menu item can open the dialog.
  open?: boolean
  onOpenChange?: (open: boolean) => void
  hideTrigger?: boolean
}

export function BulkVectorizeButton({
  notebookId,
  open: controlledOpen,
  onOpenChange,
  hideTrigger = false,
}: BulkVectorizeButtonProps) {
  const { t } = useTranslation()
  const vectorize = useVectorizeNotebookSources()

  const [uncontrolledOpen, setUncontrolledOpen] = useState(false)
  const open = controlledOpen ?? uncontrolledOpen
  const setOpen = (next: boolean) => {
    if (controlledOpen === undefined) setUncontrolledOpen(next)
    onOpenChange?.(next)
  }
  const [onlyMissing, setOnlyMissing] = useState(true)

  const handleConfirm = async () => {
    try {
      await vectorize.mutateAsync({
        notebookId,
        data: { only_missing: onlyMissing },
      })
      setOpen(false)
    } catch {
      // Toast handled by hook.
    }
  }

  return (
    <>
      {/* v0.8.130 — Phase 2b: an icon action in the Sources header (name and tooltip kept). */}
      {!hideTrigger && (
        <Button
          size="icon"
          variant="ghost"
          className="size-8"
          onClick={() => setOpen(true)}
          aria-label={t('notebooks.bulkVectorize.button')}
          title={t('notebooks.bulkVectorize.button')}
        >
          <Sparkles className="h-4 w-4" />
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('notebooks.bulkVectorize.title')}</DialogTitle>
            <DialogDescription>
              {t('notebooks.bulkVectorize.description')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="flex items-start gap-3">
              <Checkbox
                id="bulk-vectorize-only-missing"
                checked={onlyMissing}
                onCheckedChange={(v) => setOnlyMissing(v === true)}
                disabled={vectorize.isPending}
              />
              <Label
                htmlFor="bulk-vectorize-only-missing"
                className="text-sm leading-tight cursor-pointer"
              >
                {t('notebooks.bulkVectorize.onlyMissingLabel')}
              </Label>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={vectorize.isPending}
            >
              {t('filesystem.cancel')}
            </Button>
            <Button onClick={handleConfirm} disabled={vectorize.isPending}>
              {vectorize.isPending ? (
                <>
                  <LoadingSpinner size="sm" className="mr-2" />
                  {t('notebooks.bulkVectorize.submitting')}
                </>
              ) : (
                t('notebooks.bulkVectorize.confirm')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
