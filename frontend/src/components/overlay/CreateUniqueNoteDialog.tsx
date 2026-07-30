'use client'

import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useCreateUniqueOverlayNote } from '@/lib/hooks/use-overlay'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { tabFromOverlay } from './OverlayUtilityPanel'

interface CreateUniqueNoteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onOpen: (tab: OpenKnowledgeTab) => void
}

function newIdempotencyKey(): string {
  return `unique-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`
}

export function CreateUniqueNoteDialog({ open, onOpenChange, onOpen }: CreateUniqueNoteDialogProps) {
  const { t } = useTranslation()
  const create = useCreateUniqueOverlayNote()
  const requestKey = useRef<string | null>(null)
  const [title, setTitle] = useState('')
  const [createError, setCreateError] = useState(false)

  useEffect(() => {
    if (open && !requestKey.current) {
      create.reset()
      requestKey.current = newIdempotencyKey()
    }
    if (!open) {
      create.reset()
      requestKey.current = null
      setTitle('')
      setCreateError(false)
    }
  }, [create, open])

  const createNote = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmedTitle = title.trim()
    if (!trimmedTitle || !requestKey.current) return
    setCreateError(false)
    try {
      const page = await create.mutateAsync({ title: trimmedTitle, idempotencyKey: requestKey.current })
      onOpen(tabFromOverlay(page))
      onOpenChange(false)
    } catch {
      setCreateError(true)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('knowledge.overlay.newUnique')}</DialogTitle>
          <DialogDescription>{t('knowledge.overlay.writable')}</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={createNote}>
          <div className="space-y-2">
            <label htmlFor="overlay-unique-title" className="text-sm font-medium">{t('knowledge.overlay.uniqueTitle')}</label>
            <input
              id="overlay-unique-title"
              value={title}
              onChange={event => setTitle(event.target.value)}
              className="h-11 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              autoComplete="off"
              autoFocus
            />
          </div>
          <p aria-live="polite" className="sr-only">{create.isPending ? t('knowledge.overlay.creating') : ''}</p>
          {(createError || create.error) && <p role="alert" className="text-sm text-destructive">{t('knowledge.overlay.createError')}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>{t('common.cancel')}</Button>
            <Button type="submit" disabled={!title.trim() || create.isPending}>{create.isPending ? t('knowledge.overlay.creating') : t('knowledge.overlay.create')}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
