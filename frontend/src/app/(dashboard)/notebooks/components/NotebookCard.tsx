'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { NotebookResponse } from '@/lib/types/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MoreHorizontal, Archive, ArchiveRestore, Trash2, FileText, StickyNote } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useUpdateNotebook } from '@/lib/hooks/use-notebooks'
import { NotebookDeleteDialog } from './NotebookDeleteDialog'
import { useRef, useState, type CSSProperties, type MouseEvent, type PointerEvent } from 'react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getDateLocale } from '@/lib/utils/date-locale'
import { TurnIntoPodcastAction } from '@/components/podcasts/TurnIntoPodcastAction'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'
import { notebookCoverTone } from '@/lib/notebook-cover'
interface NotebookCardProps {
  notebook: NotebookResponse
  /** Position on the shelf: staggers the entrance. */
  index?: number
}

// v0.8.130 — motion is decoration: none of it runs when the OS or the app's own
// display preference asks for reduced motion.
function motionAllowed(): boolean {
  if (typeof window === 'undefined') return false
  if (document.documentElement.dataset.dnMotion === 'reduced') return false
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** How long the cover takes to swing open before the notebook itself opens. */
const OPENING_MS = 320

export function NotebookCard({ notebook, index = 0 }: NotebookCardProps) {
  const { t, language } = useTranslation()
  const router = useRouter()
  const bookRef = useRef<HTMLDivElement>(null)
  const [opening, setOpening] = useState(false)
  const href = `/notebooks/${encodeURIComponent(notebook.id)}`
  const monogram = Array.from(notebook.name.trim())[0]?.toLocaleUpperCase(language) ?? ''

  // The cover leans toward the pointer and a soft light follows it across the cloth.
  const trackPointer = (event: PointerEvent<HTMLDivElement>) => {
    const book = bookRef.current
    if (!book || event.pointerType !== 'mouse' || !motionAllowed()) return
    const box = book.getBoundingClientRect()
    const x = (event.clientX - box.left) / box.width
    const y = (event.clientY - box.top) / box.height
    book.style.setProperty('--dn-light-x', `${(x * 100).toFixed(1)}%`)
    book.style.setProperty('--dn-light-y', `${(y * 100).toFixed(1)}%`)
    book.style.setProperty('--dn-lean-x', `${((0.5 - y) * 2.4).toFixed(2)}deg`)
    book.style.setProperty('--dn-lean-y', `${((x - 0.5) * 2).toFixed(2)}deg`)
  }
  const releasePointer = () => {
    const book = bookRef.current
    if (!book) return
    for (const name of ['--dn-light-x', '--dn-light-y', '--dn-lean-x', '--dn-lean-y']) book.style.removeProperty(name)
  }

  // A plain click swings the cover open first; modified clicks (new tab) and reduced
  // motion go straight through the link.
  const openBook = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (!motionAllowed()) return
    event.preventDefault()
    if (opening) return
    setOpening(true)
    router.prefetch(href)
    window.setTimeout(() => router.push(href), OPENING_MS)
  }
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const updateNotebook = useUpdateNotebook()
  const openPodcastReview = usePodcastStudioStore((state) => state.open)
  const noReadableContent = notebook.source_count + notebook.note_count === 0

  const handleArchiveToggle = () => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { archived: !notebook.archived }
    })
  }

  return (
    <>
      {/* v0.8.130 — The whole card opens the notebook through a link laid over it, so keyboard
          and screen-reader users get a real link instead of a click-only <div>.
          The link is a direct child of this positioned root on purpose: nested in
          CardHeader (a size container) `inset-0` would only span the header, and a
          link inside the title would also stop the title truncating. Controls that
          must stay independently clickable sit above it with `relative z-10`. */}
      <div
        ref={bookRef}
        data-dn-notebook-card=""
        // v0.8.130 — a bound book: the cloth colour comes from the notebook's id, and
        // stationery.css draws the page block, the hinged cover, the spine and the band.
        data-dn-cover={notebookCoverTone(notebook.id)}
        data-dn-opening={opening ? '' : undefined}
        className="group relative rounded-xl"
        style={{ '--dn-shelf-index': index } as CSSProperties}
        onPointerMove={trackPointer}
        onPointerLeave={releasePointer}
      >
        {/* The page block under the cover: its first leaf shows when the cover lifts. */}
        <div data-dn-book-pages="" aria-hidden="true" />
        <div data-dn-book-cover="">
        <Link
          href={href}
          aria-label={notebook.name}
          className="absolute inset-0 z-[1] rounded-xl"
          onClick={openBook}
        />
        <Card 
          // v0.8.130 — Phase 3a: gap-1.5 (the default 24px gap plus the header's 44px action
          // row left a ~58px blank band between the title and the description).
          className="gap-1.5 rounded-xl border bg-card py-3 transition-colors group-hover:border-foreground/25"
        >
          <CardHeader className="pb-0">
            <div className="flex min-w-0 items-start justify-between">
              <div className="flex-1 min-w-0">
                {/* v0.8.130 — a label carries the whole name: up to three lines, never an ellipsis mid-word. */}
                <CardTitle className="text-base line-clamp-3 group-hover:text-primary transition-colors">
                  {notebook.name}
                </CardTitle>
                {notebook.archived && (
                  <Badge variant="secondary" className="mt-1">
                    {t('notebooks.archived')}
                  </Badge>
                )}
              </div>
              
            </div>
          </CardHeader>
          
          <CardContent>
            <CardDescription className="line-clamp-2 text-sm">
              {notebook.description || t('chat.noDescription')}
            </CardDescription>

          </CardContent>
        </Card>
        {/* v0.8.130 — on the cover, under the label: when it was last opened, what it
            holds, and the podcast action (stationery.css sets these in cream on the
            cloth). It is raised above the card's link so its controls work, but lets
            clicks through everywhere else: a click on the date or the counts still
            opens the notebook. */}
        <div data-dn-cover-footer="" className="pointer-events-none relative z-10 mt-2 px-1">
          <div data-dn-cover-updated="" className="text-xs text-muted-foreground">
            {t('common.updated').replace('{time}', formatDistanceToNow(new Date(notebook.updated), {
              addSuffix: true,
              locale: getDateLocale(language)
            }))}
          </div>

          <div data-dn-cover-counts="" className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span
              className="inline-flex items-center gap-1.5"
              title={notebook.source_count === 1 ? t('notebooks.notebookCard.sourceTitleOne', { count: 1 }) : t('notebooks.notebookCard.sourcesTitle', { count: notebook.source_count })}
            >
              <FileText aria-hidden="true" className="h-3 w-3" />
              {/* v0.8.130 — Phase 3a: labelled; the chips read as a bare "1" and "0". */}
              <span>{notebook.source_count === 1 ? t('notebooks.sourceCountOne') : t('notebooks.sourceCount').replace('{count}', String(notebook.source_count))}</span>
            </span>
            <span
              className="inline-flex items-center gap-1.5"
              title={notebook.note_count === 1 ? t('notebooks.notebookCard.noteTitleOne', { count: 1 }) : t('notebooks.notebookCard.notesTitle', { count: notebook.note_count })}
            >
              <StickyNote aria-hidden="true" className="h-3 w-3" />
              <span>{notebook.note_count === 1 ? t('notebooks.noteCountOne') : t('notebooks.noteCount').replace('{count}', String(notebook.note_count))}</span>
            </span>
          </div>

          {/* The podcast action, and the notebook's menu at the fore-edge. */}
          <div className="mt-3 flex items-center justify-between gap-2 [&>*]:pointer-events-auto">
            <TurnIntoPodcastAction
              selection={{ kind: 'notebook', notebookId: notebook.id }}
              destination="quick"
              disabledReason={noReadableContent ? t('notebooks.notebookCard.noReadableContent') : undefined}
              onOpen={openPodcastReview}
            />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                data-dn-cover-menu=""
                className="relative z-10 h-8 w-8 shrink-0 p-0 rounded-md opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100 transition-[opacity,background-color] duration-200 hover:bg-muted/80"
                aria-label={t('notebooks.notebookCard.actionsFor', { name: notebook.name })}
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleArchiveToggle}>
                {notebook.archived ? (
                  <>
                    <ArchiveRestore className="h-4 w-4 mr-2" />
                    {t('notebooks.unarchive')}
                  </>
                ) : (
                  <>
                    <Archive className="h-4 w-4 mr-2" />
                    {t('notebooks.archive')}
                  </>
                )}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setShowDeleteDialog(true)}
                className="text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                {t('common.delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          </div>
        </div>
        {/* Blind-stamped into the cloth: the notebook's initial. Drawn by CSS from the
            attribute, so it is ornament only: no text for a screen reader or a contrast
            check to find (it is tone on tone by design). */}
        {monogram ? <span data-dn-book-monogram={monogram} aria-hidden="true" /> : null}
        </div>
        <span data-dn-book-ribbon="" aria-hidden="true" />
      </div>

      <NotebookDeleteDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
      />
    </>
  )
}
