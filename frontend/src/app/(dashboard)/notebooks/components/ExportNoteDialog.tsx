// v0.7.105 — Export a single note as a Markdown file.
'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { FolderOpen } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useExportNote } from '@/lib/hooks/use-export'
import { useFsHome } from '@/lib/hooks/use-fs'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { DirectoryPicker } from '@/components/notebooks/DirectoryPicker'

interface ExportNoteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  noteId: string
  noteTitle: string | null
}

function slugify(text: string, fallback = 'note'): string {
  const normalized = text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
  const slug = normalized.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return slug.slice(0, 80) || fallback
}

function joinPath(dir: string, leaf: string): string {
  return `${dir.replace(/\/+$/, '')}/${leaf}`
}

export function ExportNoteDialog({
  open,
  onOpenChange,
  noteId,
  noteTitle,
}: ExportNoteDialogProps) {
  const { t } = useTranslation()
  const exportNote = useExportNote()
  const homeQuery = useFsHome(open)

  const [destination, setDestination] = useState('')
  const [destinationTouched, setDestinationTouched] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)

  const filename = useMemo(() => `${slugify(noteTitle || 'note')}.md`, [noteTitle])

  useEffect(() => {
    if (!open) return
    if (destinationTouched) return
    if (!homeQuery.data) return
    setDestination(joinPath(homeQuery.data.default_exports, filename))
  }, [open, destinationTouched, homeQuery.data, filename])

  useEffect(() => {
    if (!open) {
      setDestinationTouched(false)
      setOverwrite(false)
      setPickerOpen(false)
    }
  }, [open])

  const handlePickerSelect = (dir: string) => {
    setDestination(joinPath(dir, filename))
    setDestinationTouched(true)
  }

  const handleSubmit = async () => {
    if (!destination.trim()) return
    try {
      await exportNote.mutateAsync({
        id: noteId,
        data: { destination: destination.trim(), overwrite },
      })
      onOpenChange(false)
    } catch {
      // Toast handled by hook.
    }
  }

  const isPending = exportNote.isPending

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('notes.exportNote')}</DialogTitle>
            <DialogDescription>{t('notes.exportNoteDesc')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="export-note-destination">
                {t('notes.exportDestination')}
              </Label>
              <div className="flex gap-2">
                <Input
                  id="export-note-destination"
                  value={destination}
                  onChange={(e) => {
                    setDestination(e.target.value)
                    setDestinationTouched(true)
                  }}
                  disabled={isPending}
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setPickerOpen(true)}
                  disabled={isPending}
                  aria-label={t('filesystem.pickDirectory')}
                >
                  <FolderOpen className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Checkbox
                id="export-note-overwrite"
                checked={overwrite}
                onCheckedChange={(v) => setOverwrite(v === true)}
                disabled={isPending}
              />
              <Label
                htmlFor="export-note-overwrite"
                className="text-sm leading-tight cursor-pointer"
              >
                {t('notes.exportOverwrite')}
              </Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
              {t('filesystem.cancel')}
            </Button>
            <Button onClick={handleSubmit} disabled={isPending || !destination.trim()}>
              {isPending ? (
                <>
                  <LoadingSpinner size="sm" className="mr-2" />
                  {t('notes.exporting')}
                </>
              ) : (
                t('notes.export')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DirectoryPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        initialPath={homeQuery.data?.default_exports}
        onSelect={handlePickerSelect}
      />
    </>
  )
}
