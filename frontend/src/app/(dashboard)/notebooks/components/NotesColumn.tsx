'use client'

import { useState, useMemo } from 'react'
import { NoteResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Plus, StickyNote, Bot, User, MoreVertical, Trash2, Download, ListChecks, Podcast } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/badge'
import { NoteEditorDialog } from './NoteEditorDialog'
import { ExportNoteDialog } from './ExportNoteDialog'
import { getDateLocale } from '@/lib/utils/date-locale'
import { formatDistanceToNow } from 'date-fns'
import { ContextToggle } from '@/components/common/ContextToggle'
import type { NoteContextMode } from '@/lib/types/notebook-context'
import type { NoteContextDefault } from '@/lib/utils/source-context'
import { useDeleteNote } from '@/lib/hooks/use-notes'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

interface NotesColumnProps {
  notes?: NoteResponse[]
  isLoading: boolean
  notebookId: string
  contextSelections?: Record<string, NoteContextMode>
  onContextModeChange?: (noteId: string, mode: NoteContextMode) => void
  onBulkContextModeChange?: (action: NoteContextDefault) => void
}

export function NotesColumn({
  notes,
  isLoading,
  notebookId,
  contextSelections,
  onContextModeChange,
  onBulkContextModeChange
}: NotesColumnProps) {
  const { t, language } = useTranslation()
  const notesLabel = t('common.notes')
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [editingNote, setEditingNote] = useState<NoteResponse | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [noteToDelete, setNoteToDelete] = useState<string | null>(null)
  const [exportNote, setExportNote] = useState<NoteResponse | null>(null)
  const openPodcastReview = usePodcastStudioStore((state) => state.open)

  const deleteNote = useDeleteNote()

  // Collapsible column state
  const { notesCollapsed, toggleNotes } = useNotebookColumnsStore()
  const collapseButton = useMemo(
    () => createCollapseButton(toggleNotes, notesLabel),
    [toggleNotes, notesLabel]
  )

  const handleDeleteClick = (noteId: string) => {
    setNoteToDelete(noteId)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!noteToDelete) return

    try {
      await deleteNote.mutateAsync(noteToDelete)
      setDeleteDialogOpen(false)
      setNoteToDelete(null)
    } catch (error) {
      console.error('Failed to delete note:', error)
    }
  }

  return (
    <>
      <CollapsibleColumn
        isCollapsed={notesCollapsed}
        onToggle={toggleNotes}
        collapsedIcon={StickyNote}
        collapsedLabel={notesLabel}
      >
        <Card data-dn-column="" className="h-full flex flex-col flex-1 overflow-hidden">
          <CardHeader className="flex-shrink-0">
            {/* v0.8.130 — Phase 2b: the header holds the title and collapse only; with the
                actions beside it the title truncated to "N…" at 1280px. */}
            <div className="flex items-center gap-1">
              {/* v0.8.130 — Phase 4b: the column title is the h2 its cards sit under. */}
              <CardTitle role="heading" aria-level={2} className="min-w-0 flex-1 truncate text-base font-medium">{notesLabel}</CardTitle>
              {collapseButton}
            </div>
          </CardHeader>

          {/* v0.8.130 — Phase 2b: a full-width Write note row, bulk context beside it. */}
          <div data-dn-column-actions="" className="flex flex-none items-center gap-2 px-4 pt-3">
            <Button
              variant="outline"
              className="min-w-0 flex-1 rounded-md"
              aria-label={t('common.addNote')}
              onClick={() => {
                setEditingNote(null)
                setShowAddDialog(true)
              }}
            >
              <Plus className="h-4 w-4" />
              {/* v0.8.130 — visible "Add"; "Write Note" truncated at 1280px. */}
              <span className="truncate">{t('common.add')}</span>
            </Button>
            {onBulkContextModeChange && notes && notes.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-8" aria-label={t('sources.bulkContext')} title={t('sources.bulkContext')}>
                    <ListChecks className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => onBulkContextModeChange('include')}>
                    {t('sources.includeAllInContext')}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onBulkContextModeChange('exclude')}>
                    {t('sources.excludeAllFromContext')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>

          {/* v0.8.130 — notebook layer: the Notes body is ruled paper with a margin rule. */}
          <CardContent data-dn-ruled="" className="flex-1 overflow-y-auto min-h-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <LoadingSpinner />
              </div>
            ) : !notes || notes.length === 0 ? (
              <EmptyState
                icon={StickyNote}
                title={t('notebooks.noNotesYet')}
                description={t('sources.createFirstNote')}
              />
            ) : (
              <div className="space-y-3">
                {notes.map((note) => {
                  // v0.8.130 — same rule the inline action used: a note with no readable text has
                  // nothing to narrate, so the menu item stays visible but disabled with its reason.
                  const podcastDisabledReason = note.content?.trim() ? undefined : t('notes.noteCard.podcastNoContent')
                  return (
                  // v0.8.130 — the list sits on ruled paper: a translucent fill (no blur) lets the
                  // ruling show through, and a 2px left index tab carries the hover. Its width never
                  // changes, only its colour, so nothing shifts on hover.
                  <div
                    key={note.id}
                    data-dn-note-card=""
                    className="group relative cursor-pointer rounded-xl border border-l-2 border-l-primary/35 bg-card/90 p-3.5 transition-colors duration-200 ease-out hover:border-l-primary"
                    onClick={() => setEditingNote(note)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {note.note_type === 'ai' ? (
                          <Bot className="h-4 w-4 text-primary" />
                        ) : (
                          <User className="h-4 w-4 text-muted-foreground" />
                        )}
                        <Badge variant="secondary" className="text-xs rounded-full px-2 py-0.5">
                          {note.note_type === 'ai' ? t('common.aiGenerated') : t('common.human')}
                        </Badge>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {formatDistanceToNow(new Date(note.updated), { 
                            addSuffix: true,
                            locale: getDateLocale(language)
                          })}
                        </span>

                        {/* Context toggle - only show if handler provided */}
                        {onContextModeChange && contextSelections?.[note.id] && (
                          <div onClick={(event) => event.stopPropagation()}>
                            <ContextToggle<NoteContextMode>
                              mode={contextSelections[note.id]}
                              hasInsights={false}
                              onChange={(mode) => onContextModeChange(note.id, mode)}
                            />
                          </div>
                        )}

                        {/* v0.8.130 — the note's actions menu now also holds "Turn into podcast"; it needs a
                            name and must show on keyboard focus, not only on hover. */}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={t('notes.noteCard.noteActions')}
                              title={t('notes.noteCard.noteActions')}
                              className="h-7 w-7 p-0 rounded-md opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(hover:none)]:opacity-100 transition-[opacity,background-color] duration-150 hover:bg-muted/80"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-48">
                            {/* v0.8.130 — moved here from a full-width row on every card (as SourceCard
                                does it). Side-effect free: it only opens the podcast review. */}
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation()
                                openPodcastReview([{ kind: 'app_note', noteId: note.id }], 'quick')
                              }}
                              disabled={Boolean(podcastDisabledReason)}
                            >
                              <Podcast className="h-4 w-4 mr-2" />
                              {podcastDisabledReason
                                ? t('notes.noteCard.turnIntoPodcastDisabled', { reason: podcastDisabledReason })
                                : t('notes.noteCard.turnIntoPodcast')}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation()
                                setExportNote(note)
                              }}
                            >
                              <Download className="h-4 w-4 mr-2" />
                              {t('notes.export')}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteClick(note.id)
                              }}
                              className="text-destructive focus:text-destructive"
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              {t('notebooks.deleteNote')}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>

                    {note.title && (
                      <h4 className="text-sm font-medium mb-1.5 break-words transition-colors group-hover:text-primary">{note.title}</h4>
                    )}

                    {note.content && (
                      <p data-dn-reading="" className="text-sm text-muted-foreground line-clamp-3 break-words leading-relaxed">
                        {note.content}
                      </p>
                    )}
                  </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </CollapsibleColumn>

      <NoteEditorDialog
        open={showAddDialog || Boolean(editingNote)}
        onOpenChange={(open) => {
          if (!open) {
            setShowAddDialog(false)
            setEditingNote(null)
          } else {
            setShowAddDialog(true)
          }
        }}
        notebookId={notebookId}
        note={editingNote ?? undefined}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title={t('notebooks.deleteNote')}
        description={t('notebooks.deleteNoteConfirm')}
        confirmText={t('common.delete')}
        onConfirm={handleDeleteConfirm}
        isLoading={deleteNote.isPending}
        confirmVariant="destructive"
      />

      <ExportNoteDialog
        open={exportNote !== null}
        onOpenChange={(open) => {
          if (!open) setExportNote(null)
        }}
        noteId={exportNote?.id ?? ''}
        noteTitle={exportNote?.title ?? null}
      />
    </>
  )
}
