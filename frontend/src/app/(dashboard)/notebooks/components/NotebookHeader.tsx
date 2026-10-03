'use client'

import { useState } from 'react'
import { NotebookResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Archive, ArchiveRestore, Download, Info, MoreHorizontal, Sparkles, Trash2 } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useUpdateNotebook } from '@/lib/hooks/use-notebooks'
import { NotebookDeleteDialog } from './NotebookDeleteDialog'
import { ExportNotebookDialog } from './ExportNotebookDialog'
import { ExecutiveSynthesisDialog } from '@/components/notebooks/ExecutiveSynthesisDialog'
import { formatDistanceToNow } from 'date-fns'
import { getDateLocale } from '@/lib/utils/date-locale'
import { InlineEdit } from '@/components/common/InlineEdit'
import { MindMapButton } from '@/components/notebooks/MindMapButton'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotebookHeaderProps {
  notebook: NotebookResponse
}

export function NotebookHeader({ notebook }: NotebookHeaderProps) {
  const { t, language } = useTranslation()
  const dfLocale = getDateLocale(language)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showExportDialog, setShowExportDialog] = useState(false)
  const [showSynthesisDialog, setShowSynthesisDialog] = useState(false)
  
  const updateNotebook = useUpdateNotebook()

  const handleUpdateName = async (name: string) => {
    if (!name || name === notebook.name) return
    
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: { name }
    })
  }

  const handleUpdateDescription = async (description: string) => {
    if (description === notebook.description) return
    
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: { description: description || undefined }
    })
  }

  const handleArchiveToggle = () => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { archived: !notebook.archived }
    })
  }

  const created = t('common.created').replace('{time}', formatDistanceToNow(new Date(notebook.created), { addSuffix: true, locale: dfLocale }))
  const updated = t('common.updated').replace('{time}', formatDistanceToNow(new Date(notebook.updated), { addSuffix: true, locale: dfLocale }))

  // v0.8.130 — Phase 2a: a 56px top bar instead of a ~200px header. The editable
  // title is the page's single h1 (the workspace <main> is labelled by it); the
  // description and dates moved behind "About this notebook"; Archive, Export and
  // Delete moved into the "Notebook actions" menu (a red Delete pill sat among the
  // primary actions). Synthesis and Mind map stay one click away.
  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-1">
        <h1 id="notebook-title" className="min-w-0 flex-1 text-xl font-semibold tracking-tight">
          <InlineEdit
            id="notebook-name"
            name="notebook-name"
            value={notebook.name}
            onSave={handleUpdateName}
            className="min-w-0 truncate text-xl font-semibold"
            inputClassName="text-xl font-semibold"
            placeholder={t('notebooks.namePlaceholder')}
          />
        </h1>
        {notebook.archived && (
          <Badge variant="secondary">{t('notebooks.archived')}</Badge>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowSynthesisDialog(true)}
          className="gap-1.5"
          data-testid="executive-synthesis-button"
          aria-label={t('notebooks.notebookHeader.synthesis')}
        >
          <Sparkles className="h-4 w-4" />
          {/* v0.8.130 — icon-only below 640px so the title keeps room. */}
          <span className="hidden sm:inline">{t('notebooks.notebookHeader.synthesis')}</span>
        </Button>
        <MindMapButton notebookId={notebook.id} />
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t('notebooks.aboutNotebook')} title={t('notebooks.aboutNotebook')}>
              <Info className="h-4 w-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 space-y-3">
            <InlineEdit
              id="notebook-description"
              name="notebook-description"
              value={notebook.description || ''}
              onSave={handleUpdateDescription}
              className="text-sm text-muted-foreground"
              inputClassName="text-sm text-muted-foreground"
              placeholder={t('notebooks.addDescription')}
              multiline
              emptyText={t('notebooks.addDescription')}
            />
            <p className="text-xs text-muted-foreground">
              {/* v0.8.130 — explicit separator: JSX trims the space before a line break, which rendered
                  "ago •Updated". */}
              {created}{' • '}{updated}
            </p>
          </PopoverContent>
        </Popover>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t('notebooks.actions')} title={t('notebooks.actions')}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={handleArchiveToggle}>
              {notebook.archived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
              {notebook.archived ? t('notebooks.unarchive') : t('notebooks.archive')}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setShowExportDialog(true)}>
              <Download className="h-4 w-4" />
              {t('notebooks.export.button')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setShowDeleteDialog(true)}>
              <Trash2 className="h-4 w-4" />
              {t('common.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <NotebookDeleteDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
        redirectAfterDelete
      />

      <ExportNotebookDialog
        open={showExportDialog}
        onOpenChange={setShowExportDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
      />

      <ExecutiveSynthesisDialog
        open={showSynthesisDialog}
        onOpenChange={setShowSynthesisDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
      />
    </>
  )
}
