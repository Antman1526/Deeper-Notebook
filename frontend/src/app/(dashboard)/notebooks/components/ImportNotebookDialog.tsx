// v0.7.119 — Notebook import dialog with dry-run preview.
//
// Two-step flow:
//   1. User picks a source path (folder / .zip / .md), hits Preview →
//      POST /notebooks/import/preview returns the planned notebook
//      name, description, and note / source lists without touching
//      the domain layer.
//   2. User edits the name / description, picks "new vs existing"
//      mode, and confirms → POST /notebooks/import commits.
//
// Implementation notes:
//   - The DirectoryPicker is opened in `selectionMode='any'` so the
//     user can pick a file (.zip or .md) as well as a folder.
//   - Warnings from preview surface as a yellow Alert.
//   - Overview notes (📋) are flagged in the lists per the v0.7.89
//     manifest convention.
//   - On success we navigate to the new/target notebook so the user
//     can immediately see the imported content.
'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
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
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { AlertTriangle, FolderOpen } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useFsHome } from '@/lib/hooks/use-fs'
import {
  useImportPreview,
  useImportNotebook,
  useNotebooks,
} from '@/lib/hooks/use-notebooks'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { DirectoryPicker } from '@/components/notebooks/DirectoryPicker'
import {
  ImportMode,
  NotebookImportPreviewItem,
  NotebookImportPreviewResponse,
} from '@/lib/types/api'

interface ImportNotebookDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function ItemRow({ item }: { item: NotebookImportPreviewItem }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 px-2 text-sm rounded hover:bg-accent/40">
      <div className="flex items-center gap-2 min-w-0">
        {item.is_overview ? (
          <span aria-hidden className="text-base leading-none">
            📋
          </span>
        ) : null}
        <span className="truncate">{item.title}</span>
      </div>
      <span className="text-xs text-muted-foreground shrink-0">
        {formatBytes(item.bytes)}
      </span>
    </div>
  )
}

export function ImportNotebookDialog({
  open,
  onOpenChange,
}: ImportNotebookDialogProps) {
  const { t } = useTranslation()
  const router = useRouter()
  const homeQuery = useFsHome(open)
  const { data: notebooks } = useNotebooks(false)

  const previewMutation = useImportPreview()
  const importMutation = useImportNotebook()

  const [sourcePath, setSourcePath] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [preview, setPreview] = useState<NotebookImportPreviewResponse | null>(
    null,
  )
  const [newName, setNewName] = useState('')
  const [description, setDescription] = useState('')
  const [mode, setMode] = useState<ImportMode>('new')
  const [targetNotebookId, setTargetNotebookId] = useState<string>('')
  const [importSources, setImportSources] = useState(true)

  // Reset state when the dialog closes.
  useEffect(() => {
    if (!open) {
      setSourcePath('')
      setPickerOpen(false)
      setPreview(null)
      setNewName('')
      setDescription('')
      setMode('new')
      setTargetNotebookId('')
      setImportSources(true)
      previewMutation.reset()
      importMutation.reset()
    }
    // We only want to reset on close; the mutations are stable refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handlePreview = async () => {
    const path = sourcePath.trim()
    if (!path) return
    try {
      const result = await previewMutation.mutateAsync({ source_path: path })
      setPreview(result)
      setNewName(result.notebook_name_hint ?? '')
      setDescription(result.description_hint ?? '')
    } catch {
      // Toast handled by hook.
    }
  }

  const handleConfirm = async () => {
    if (!preview) return
    if (mode === 'into_existing' && !targetNotebookId) return
    try {
      const response = await importMutation.mutateAsync({
        source_path: preview.source_path,
        mode,
        target_notebook_id:
          mode === 'into_existing' ? targetNotebookId : null,
        new_name: mode === 'new' ? newName.trim() || null : null,
        import_sources: importSources,
      })
      onOpenChange(false)
      router.push(`/notebooks/${response.notebook_id}`)
    } catch {
      // Toast handled by hook.
    }
  }

  const detectedKindBadge = useMemo(() => {
    if (!preview) return null
    return (
      <Badge variant="secondary" data-testid="import-detected-kind">
        {preview.detected_kind}
      </Badge>
    )
  }, [preview])

  const isPreviewPending = previewMutation.isPending
  const isImportPending = importMutation.isPending

  const canConfirm =
    !!preview &&
    !isImportPending &&
    (mode === 'new'
      ? newName.trim().length > 0
      : targetNotebookId.length > 0)

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('notebooks.import.title')}</DialogTitle>
            <DialogDescription>
              {t('notebooks.import.description')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="import-source-path">
                {t('notebooks.import.sourcePathLabel')}
              </Label>
              <div className="flex gap-2">
                <Input
                  id="import-source-path"
                  value={sourcePath}
                  onChange={(e) => setSourcePath(e.target.value)}
                  disabled={isPreviewPending || isImportPending}
                  placeholder={t('notebooks.import.sourcePathPlaceholder')}
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setPickerOpen(true)}
                  disabled={isPreviewPending || isImportPending}
                  aria-label={t('filesystem.pickDirectory')}
                >
                  <FolderOpen className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handlePreview}
                  disabled={
                    !sourcePath.trim() || isPreviewPending || isImportPending
                  }
                >
                  {isPreviewPending ? (
                    <>
                      <LoadingSpinner size="sm" className="mr-2" />
                      {t('notebooks.import.previewLoading')}
                    </>
                  ) : (
                    t('notebooks.import.preview')
                  )}
                </Button>
              </div>
            </div>

            {preview && (
              <>
                {preview.warnings.length > 0 && (
                  <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('common.warning')}</AlertTitle>
                    <AlertDescription>
                      <ul className="list-disc pl-4 space-y-1">
                        {preview.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                )}

                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    {t('notebooks.import.detectedKind')}
                  </span>
                  {detectedKindBadge}
                </div>

                <div className="space-y-2">
                  <Label>{t('notebooks.import.modeLabel')}</Label>
                  <RadioGroup
                    value={mode}
                    onValueChange={(v) => setMode(v as ImportMode)}
                    disabled={isImportPending}
                  >
                    <div className="flex items-center gap-2">
                      <RadioGroupItem value="new" id="import-mode-new" />
                      <Label
                        htmlFor="import-mode-new"
                        className="text-sm cursor-pointer"
                      >
                        {t('notebooks.import.modeNew')}
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <RadioGroupItem
                        value="into_existing"
                        id="import-mode-existing"
                      />
                      <Label
                        htmlFor="import-mode-existing"
                        className="text-sm cursor-pointer"
                      >
                        {t('notebooks.import.modeExisting')}
                      </Label>
                    </div>
                  </RadioGroup>
                </div>

                {mode === 'new' ? (
                  <div className="grid grid-cols-1 gap-3">
                    <div className="space-y-2">
                      <Label htmlFor="import-new-name">
                        {t('notebooks.import.newNameLabel')}
                      </Label>
                      <Input
                        id="import-new-name"
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        disabled={isImportPending}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="import-description">
                        {t('notebooks.import.descriptionLabel')}
                      </Label>
                      <Textarea
                        id="import-description"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        rows={2}
                        disabled={isImportPending}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label htmlFor="import-target-notebook">
                      {t('notebooks.import.targetNotebookLabel')}
                    </Label>
                    <Select
                      value={targetNotebookId}
                      onValueChange={setTargetNotebookId}
                      disabled={isImportPending}
                    >
                      <SelectTrigger
                        id="import-target-notebook"
                        className="w-full"
                        aria-label={t(
                          'notebooks.import.targetNotebookLabel',
                        )}
                      >
                        <SelectValue
                          placeholder={t(
                            'notebooks.import.targetNotebookPlaceholder',
                          )}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {(notebooks ?? []).map((nb) => (
                          <SelectItem key={nb.id} value={nb.id}>
                            {nb.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                <div className="flex items-start gap-3">
                  <Checkbox
                    id="import-sources-check"
                    checked={importSources}
                    onCheckedChange={(v) => setImportSources(v === true)}
                    disabled={isImportPending}
                  />
                  <Label
                    htmlFor="import-sources-check"
                    className="text-sm leading-tight cursor-pointer"
                  >
                    {t('notebooks.import.includeSourcesCheck')}
                  </Label>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="border rounded-md">
                    <div className="px-3 py-2 border-b text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {t('notebooks.import.notesHeading')} ({preview.notes.length})
                    </div>
                    <ScrollArea className="h-40">
                      <div className="p-1">
                        {preview.notes.length === 0 ? (
                          <p className="text-xs text-muted-foreground p-2">
                            {t('notebooks.import.empty')}
                          </p>
                        ) : (
                          preview.notes.map((n) => (
                            <ItemRow key={n.relative_path} item={n} />
                          ))
                        )}
                      </div>
                    </ScrollArea>
                  </div>

                  <div className="border rounded-md">
                    <div className="px-3 py-2 border-b text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {t('notebooks.import.sourcesHeading')} ({preview.sources.length})
                    </div>
                    <ScrollArea className="h-40">
                      <div className="p-1">
                        {preview.sources.length === 0 ? (
                          <p className="text-xs text-muted-foreground p-2">
                            {t('notebooks.import.empty')}
                          </p>
                        ) : (
                          preview.sources.map((s) => (
                            <ItemRow key={s.relative_path} item={s} />
                          ))
                        )}
                      </div>
                    </ScrollArea>
                  </div>
                </div>
              </>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isImportPending}
            >
              {t('filesystem.cancel')}
            </Button>
            <Button onClick={handleConfirm} disabled={!canConfirm}>
              {isImportPending ? (
                <>
                  <LoadingSpinner size="sm" className="mr-2" />
                  {t('notebooks.import.confirmLoading')}
                </>
              ) : (
                t('notebooks.import.confirm')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DirectoryPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        initialPath={homeQuery.data?.default_exports}
        selectionMode="any"
        onSelect={(path) => setSourcePath(path)}
      />
    </>
  )
}
