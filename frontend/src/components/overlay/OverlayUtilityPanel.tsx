'use client'

import { useState } from 'react'
import { CalendarDays, FilePlus2, FileText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { OverlayPage } from '@/lib/api/overlay'
import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { useOverlayNotes } from '@/lib/hooks/use-overlay'
import { useTranslation } from '@/lib/hooks/use-translation'

interface OverlayUtilityPanelProps {
  onOpen: (tab: OpenKnowledgeTab) => void
  onNewUnique: () => void
  onToday: () => Promise<void>
  todayPending?: boolean
  todayError?: boolean
}

export function localDateKey(now = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function tabFromOverlay(page: OverlayPage): OpenKnowledgeTab {
  return {
    sourceAuthority: 'overlay',
    vaultId: page.overlay.space_id,
    noteId: page.overlay.id,
    title: page.overlay.title,
    relativePath: page.overlay.relative_path,
    viewMode: 'source',
  }
}

export function OverlayUtilityPanel({
  onOpen,
  onNewUnique,
  onToday,
  todayPending = false,
  todayError = false,
}: OverlayUtilityPanelProps) {
  const { t } = useTranslation()
  const notes = useOverlayNotes()
  const [localTodayError, setLocalTodayError] = useState(false)
  const daily = notes.data?.filter(note => note.kind === 'daily') || []
  const unique = notes.data?.filter(note => note.kind === 'unique') || []

  const openToday = async () => {
    setLocalTodayError(false)
    try {
      await onToday()
    } catch {
      setLocalTodayError(true)
    }
  }

  return (
    <section className="space-y-3" aria-labelledby="overlay-root-heading">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="overlay-root-heading" className="text-sm font-semibold">
            {t('knowledge.overlay.name')}
          </h2>
          <Badge variant="secondary" className="mt-1">{t('knowledge.overlay.writable')}</Badge>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Button type="button" className="h-auto min-h-11 min-w-0 whitespace-normal py-2 leading-tight" onClick={() => void openToday()} disabled={todayPending}>
          <CalendarDays className="h-4 w-4" aria-hidden="true" />
          {t('knowledge.overlay.today')}
        </Button>
        <Button type="button" variant="outline" className="h-auto min-h-11 min-w-0 whitespace-normal py-2 leading-tight" onClick={onNewUnique}>
          <FilePlus2 className="h-4 w-4" aria-hidden="true" />
          {t('knowledge.overlay.newUnique')}
        </Button>
      </div>
      <div aria-live="polite" className="space-y-2">
        {notes.isLoading && <p role="status" className="text-sm text-muted-foreground">{t('knowledge.filesLoading')}</p>}
        {notes.isError && <p role="alert" className="text-sm text-destructive">{t('knowledge.overlay.loadError')}</p>}
        {!notes.isLoading && daily.length === 0 && unique.length === 0 && (
          <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">{t('knowledge.overlay.empty')}</p>
        )}
        {(localTodayError || todayError) && <p role="alert" className="text-sm text-destructive">{t('knowledge.overlay.createError')}</p>}
        {daily.length > 0 && <OverlayNoteGroup heading={t('knowledge.overlay.daily')} notes={daily} onOpen={onOpen} />}
        {unique.length > 0 && <OverlayNoteGroup heading={t('knowledge.overlay.notes')} notes={unique} onOpen={onOpen} />}
      </div>
    </section>
  )
}

function OverlayNoteGroup({ heading, notes, onOpen }: {
  heading: string
  notes: NonNullable<ReturnType<typeof useOverlayNotes>['data']>
  onOpen: (tab: OpenKnowledgeTab) => void
}) {
  return (
    <section aria-label={heading}>
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{heading}</h3>
      <ul className="space-y-1" role="list">
        {notes.map(note => (
          <li key={note.id}>
            <button
              type="button"
              className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => onOpen({ sourceAuthority: 'overlay', vaultId: note.space_id, noteId: note.id, title: note.title, relativePath: note.relative_path, viewMode: 'source' })}
            >
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="truncate">{note.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
