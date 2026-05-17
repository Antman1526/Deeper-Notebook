// v0.7.105 — Export a notebook to disk. Lets the user pick folder-vs-zip,
// destination path, whether to include source documents, and whether
// to overwrite. Defaults destination to
// `{default_exports}/{notebook-slug}` or `.zip` based on format.
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { FolderOpen } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useExportNotebook } from '@/lib/hooks/use-export'
import { useFsHome } from '@/lib/hooks/use-fs'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { DirectoryPicker } from '@/components/notebooks/DirectoryPicker'
import { ExportFormat } from '@/lib/types/api'

interface ExportNotebookDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
  notebookName: string
}

function slugify(text: string, fallback = 'notebook'): string {
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

export function ExportNotebookDialog({
  open,
  onOpenChange,
  notebookId,
  notebookName,
}: ExportNotebookDialogProps) {
  const { t } = useTranslation()
  const exportNotebook = useExportNotebook()
  const homeQuery = useFsHome(open)

  const [format, setFormat] = useState<ExportFormat>('folder')
  const [destination, setDestination] = useState('')
  const [destinationTouched, setDestinationTouched] = useState(false)
  const [includeSources, setIncludeSources] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)

  const slug = useMemo(() => slugify(notebookName), [notebookName])

  // Auto-populate destination from home + slug + format when the user
  // hasn't customized it. Re-derive whenever format flips.
  useEffect(() => {
    if (!open) return
    if (destinationTouched) return
    if (!homeQuery.data) return
    const base = homeQuery.data.default_exports
    const leaf = format === 'zip' ? `${slug}.zip` : slug
    setDestination(joinPath(base, leaf))
  }, [open, destinationTouched, homeQuery.data, format, slug])

  // Reset state when dialog closes.
  useEffect(() => {
    if (!open) {
      setFormat('folder')
      setDestinationTouched(false)
      setIncludeSources(false)
      setOverwrite(false)
      setPickerOpen(false)
    }
  }, [open])

  const handlePickerSelect = (path: string) => {
    const leaf = format === 'zip' ? `${slug}.zip` : slug
    setDestination(joinPath(path, leaf))
    setDestinationTouched(true)
  }

  const handleSubmit = async () => {
    if (!destination.trim()) return
    try {
      await exportNotebook.mutateAsync({
        id: notebookId,
        data: {
          destination: destination.trim(),
          format,
          include_sources: includeSources,
          overwrite,
        },
      })
      onOpenChange(false)
    } catch {
      // Toast is handled by the mutation hook.
    }
  }

  const isPending = exportNotebook.isPending

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('notebooks.exportNotebook')}</DialogTitle>
            <DialogDescription>
              {t('notebooks.exportNotebookDesc').replace('{name}', notebookName)}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>{t('notebooks.exportFormatLabel')}</Label>
              <RadioGroup
                value={format}
                onValueChange={(value) => setFormat(value as ExportFormat)}
                disabled={isPending}
              >
                <div className="flex items-center space-x-3">
                  <RadioGroupItem value="folder" id="export-fmt-folder" />
                  <Label htmlFor="export-fmt-folder" className="text-sm cursor-pointer">
                    {t('notebooks.exportFormat.folder')}
                  </Label>
                </div>
                <div className="flex items-center space-x-3">
                  <RadioGroupItem value="zip" id="export-fmt-zip" />
                  <Label htmlFor="export-fmt-zip" className="text-sm cursor-pointer">
                    {t('notebooks.exportFormat.zip')}
                  </Label>
                </div>
              </RadioGroup>
            </div>

            <div className="space-y-2">
              <Label htmlFor="export-destination">
                {t('notebooks.exportDestination')}
              </Label>
              <div className="flex gap-2">
                <Input
                  id="export-destination"
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
                id="export-include-sources"
                checked={includeSources}
                onCheckedChange={(v) => setIncludeSources(v === true)}
                disabled={isPending}
              />
              <Label
                htmlFor="export-include-sources"
                className="text-sm leading-tight cursor-pointer"
              >
                {t('notebooks.exportIncludeSources')}
              </Label>
            </div>

            <div className="flex items-start gap-3">
              <Checkbox
                id="export-overwrite"
                checked={overwrite}
                onCheckedChange={(v) => setOverwrite(v === true)}
                disabled={isPending}
              />
              <Label
                htmlFor="export-overwrite"
                className="text-sm leading-tight cursor-pointer"
              >
                {t('notebooks.exportOverwrite')}
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
                  {t('notebooks.exporting')}
                </>
              ) : (
                t('notebooks.export')
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
