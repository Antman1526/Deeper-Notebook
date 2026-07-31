'use client'

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { EditorView } from '@codemirror/view'
import {
  AlertTriangle,
  Check,
  FilePenLine,
  RefreshCw,
} from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { VaultGraph } from '@/components/vault/VaultGraph'
import { VaultLinks } from '@/components/vault/VaultLinks'
import { VaultLivePreview } from '@/components/vault/VaultLivePreview'
import { VaultMarkdown } from '@/components/vault/VaultMarkdown'
import type { KnowledgeViewMode } from '@/lib/api/knowledge-workspace'
import type { GraphViewport } from '@/lib/api/knowledge-workspace'
import type { OverlayPage } from '@/lib/api/overlay'
import { useUpdateOverlayNote } from '@/lib/hooks/use-overlay'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useOverlayDraftStore } from '@/lib/stores/overlay-draft-store'
import {
  buildMarkdownModel,
  type HeadingDescriptor,
} from '@/lib/vault/markdown-model'

import { OverlaySourceEditor } from './OverlaySourceEditor'

interface OverlayDocumentViewProps {
  viewId?: string
  mode: KnowledgeViewMode
  page: OverlayPage
  onNavigate: (noteId: string) => void
  onMarkdownChange?: (markdown: string) => void
  onReload?: () => Promise<OverlayPage | undefined>
  workspacePaneId?: string
  workspaceTabId?: string
  graphViewport?: GraphViewport
  onGraphViewportChange?: (viewport: GraphViewport) => void
}

type SaveStatus = 'idle' | 'saved' | 'error' | 'conflict'

interface Draft {
  title: string
  markdown: string
}

function pageMarkdown(page: OverlayPage): string {
  return page.editable_markdown
}

function draftFromPage(page: OverlayPage): Draft {
  return {
    title: page.overlay.title,
    markdown: pageMarkdown(page),
  }
}

function draftFingerprint(draft: Draft): string {
  return `${draft.title.length}:${draft.title}\0${draft.markdown.length}:${draft.markdown}`
}

function pageFingerprint(page: OverlayPage): string {
  return `${page.overlay.id}:${page.overlay.revision}:${page.overlay.content_hash}`
}

function newSaveKey(): string {
  return `save-${globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`
}

function isRevisionConflict(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const response = (error as {
    response?: { data?: { detail?: { code?: unknown } } }
  }).response
  return response?.data?.detail?.code === 'overlay_revision_conflict'
    || (error as { code?: unknown }).code === 'overlay_revision_conflict'
    || (error as { message?: unknown }).message === 'overlay_revision_conflict'
}

function encodeIdPrefix(value: string): string {
  return `o-${Array.from(value, (character) => (
    character.charCodeAt(0).toString(16).padStart(4, '0')
  )).join('') || 'empty'}`
}

function displayProperty(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || typeof value !== 'object') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return '[Unserializable]'
  }
}

export function OverlayDocumentView({
  viewId = 'overlay',
  mode,
  page,
  onNavigate,
  onMarkdownChange,
  onReload,
  workspacePaneId,
  workspaceTabId,
  graphViewport,
  onGraphViewportChange,
}: OverlayDocumentViewProps) {
  const { t } = useTranslation()
  const update = useUpdateOverlayNote()
  const containerRef = useRef<HTMLElement>(null)
  const reviewButtonRef = useRef<HTMLButtonElement>(null)
  const saveStoredDraft = useOverlayDraftStore((state) => state.saveDraft)
  const clearStoredDraft = useOverlayDraftStore((state) => state.clearDraft)
  const [initialSnapshot] = useState(() => {
    const stored = useOverlayDraftStore.getState().drafts[viewId]
    return stored?.noteId === page.overlay.id ? stored : null
  })
  const [loadedPage, setLoadedPage] = useState(
    () => initialSnapshot?.loadedPage ?? page,
  )
  const [draft, setDraft] = useState<Draft>(() => initialSnapshot
    ? { title: initialSnapshot.title, markdown: initialSnapshot.markdown }
    : draftFromPage(page))
  const draftRef = useRef(draft)
  const [saving, setSaving] = useState(false)
  const [reloading, setReloading] = useState(false)
  const [reloadError, setReloadError] = useState(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [reloadDialogOpen, setReloadDialogOpen] = useState(false)

  const loadedDraft = useMemo(() => draftFromPage(loadedPage), [loadedPage])
  const loadedContentFingerprint = `${
    loadedPage.overlay.content_hash
  }:${draftFingerprint(loadedDraft)}`
  const localContentFingerprint = `${
    loadedPage.overlay.content_hash
  }:${draftFingerprint(draft)}`
  const isDirty = localContentFingerprint !== loadedContentFingerprint
  const markdown = draft.markdown.replace(/\r(?!\n)/g, '\n')
  const model = useMemo(() => buildMarkdownModel(markdown), [markdown])
  const headingIdPrefix = useMemo(() => encodeIdPrefix(viewId), [viewId])
  const displayOutgoingLinks = useMemo(
    () => loadedPage.outgoing_links.map((link) => (
      link.target_overlay_note_id
        ? link
        : { ...link, resolved: false }
    )),
    [loadedPage.outgoing_links],
  )
  const displayBacklinks = useMemo(
    () => loadedPage.backlinks.map((link) => (
      link.source_overlay_note_id && link.source_relative_path
        ? link
        : { ...link, resolved: false }
    )),
    [loadedPage.backlinks],
  )
  const unresolved = displayOutgoingLinks.filter((link) => !link.resolved)
  const title = draft.title.trim() || t('knowledge.untitledNote')
  const properties = Object.entries(loadedPage.note.properties || {})
  const tags = Array.from(new Set(loadedPage.note.tags || []))
  const busy = saving || reloading

  useEffect(() => {
    onMarkdownChange?.(draftRef.current.markdown)
  }, [onMarkdownChange])

  const adoptPage = useCallback((nextPage: OverlayPage) => {
    const nextDraft = draftFromPage(nextPage)
    setLoadedPage(nextPage)
    draftRef.current = nextDraft
    setDraft(nextDraft)
    onMarkdownChange?.(nextDraft.markdown)
    clearStoredDraft(viewId)
  }, [clearStoredDraft, onMarkdownChange, viewId])

  useEffect(() => {
    if (loadedPage.overlay.id !== page.overlay.id) {
      adoptPage(page)
      setSaveStatus('idle')
      setReloadError(false)
      return
    }
    if (pageFingerprint(loadedPage) === pageFingerprint(page)) return
    if (page.overlay.revision < loadedPage.overlay.revision || isDirty) return

    adoptPage(page)
    setSaveStatus('idle')
    setReloadError(false)
  }, [adoptPage, isDirty, loadedPage, page])

  const changeDraft = (change: Partial<Draft>) => {
    const nextDraft = { ...draftRef.current, ...change }
    draftRef.current = nextDraft
    setDraft(nextDraft)
    onMarkdownChange?.(nextDraft.markdown)
    if (draftFingerprint(nextDraft) === draftFingerprint(loadedDraft)) {
      clearStoredDraft(viewId)
    } else {
      saveStoredDraft(viewId, {
        noteId: loadedPage.overlay.id,
        loadedPage,
        title: nextDraft.title,
        markdown: nextDraft.markdown,
      })
    }
    setSaveStatus('idle')
    setReloadError(false)
  }

  const save = async () => {
    const canonicalTitle = draft.title.trim()
    if (!canonicalTitle || !isDirty || busy) return

    setSaving(true)
    setSaveStatus('idle')
    setReloadError(false)
    try {
      const updated = await update.mutateAsync({
        id: loadedPage.overlay.id,
        title: canonicalTitle,
        markdown: draft.markdown,
        expectedRevision: loadedPage.overlay.revision,
        idempotencyKey: newSaveKey(),
      })
      adoptPage(updated)
      setSaveStatus('saved')
    } catch (error) {
      setSaveStatus(isRevisionConflict(error) ? 'conflict' : 'error')
    } finally {
      setSaving(false)
    }
  }

  const reloadServer = async () => {
    if (reloading) return
    setReloading(true)
    setReloadError(false)
    try {
      if (!onReload) throw new Error('overlay_reload_unavailable')
      const refreshed = await onReload()
      if (
        !refreshed
        || refreshed.overlay.id !== loadedPage.overlay.id
        || refreshed.overlay.revision <= loadedPage.overlay.revision
      ) {
        throw new Error('overlay_reload_stale')
      }
      adoptPage(refreshed)
      setSaveStatus('idle')
    } catch {
      setReloadError(true)
    } finally {
      setReloading(false)
    }
  }

  const changeReloadDialog = (open: boolean) => {
    setReloadDialogOpen(open)
    if (!open) {
      setTimeout(() => reviewButtonRef.current?.focus(), 0)
    }
  }

  const onHeading = (heading: HeadingDescriptor) => {
    const container = containerRef.current
    if (!container) return
    if (mode === 'reading') {
      const target = Array.from(
        container.querySelectorAll<HTMLElement>('[data-heading-slug]'),
      ).find((candidate) => candidate.dataset.headingSlug === heading.slug)
      target?.scrollIntoView({ block: 'start' })
      return
    }
    if (mode === 'graph') return
    const editor = container.querySelector<HTMLElement>('[role="textbox"]')
    if (!editor) return
    const view = EditorView.findFromDOM(editor)
    if (!view) return
    const offset = Math.max(0, Math.min(heading.sourceFrom, view.state.doc.length))
    view.dispatch({
      selection: { anchor: offset },
      effects: EditorView.scrollIntoView(offset, { y: 'center' }),
    })
  }

  const projectionKey = loadedPage.overlay.projection_state === 'pending'
    ? 'knowledge.overlay.projectionPending'
    : loadedPage.overlay.projection_state === 'failed'
      ? 'knowledge.overlay.projectionFailed'
      : loadedPage.overlay.projection_state === 'conflict'
        ? 'knowledge.overlay.projectionConflict'
        : 'knowledge.overlay.projectionCurrent'

  const document = mode === 'source' ? (
    <div className="dn-overlay-source-view">
      <div className="space-y-2 border-b p-3">
        <label htmlFor={`${headingIdPrefix}-title`} className="text-sm font-medium">
          {t('common.title')}
        </label>
        <Input
          id={`${headingIdPrefix}-title`}
          value={draft.title}
          disabled={busy}
          onChange={(event) => changeDraft({ title: event.target.value })}
        />
      </div>
      <OverlaySourceEditor
        ariaLabel={`${title} source`}
        markdown={draft.markdown}
        disabled={busy}
        onChange={(nextMarkdown) => changeDraft({ markdown: nextMarkdown })}
      />
    </div>
  ) : mode === 'reading' ? (
    <section aria-label={`${title} reading view`}>
      <VaultMarkdown
        noteId={loadedPage.note.id}
        headingIdPrefix={headingIdPrefix}
        markdown={markdown}
        links={displayOutgoingLinks}
        onNavigate={onNavigate}
        footnoteLabel={t('knowledge.footnotes')}
      />
    </section>
  ) : mode === 'live-preview' ? (
    <VaultLivePreview
      title={title}
      markdown={markdown}
      links={displayOutgoingLinks}
      onNavigate={onNavigate}
    />
  ) : (
    <VaultGraph
      graph={loadedPage.graph ?? undefined}
      unresolved={unresolved}
      onNavigate={onNavigate}
      viewport={graphViewport}
      onMoveEnd={(viewport) => {
        if (workspacePaneId && workspaceTabId) onGraphViewportChange?.(viewport)
      }}
    />
  )

  return (
    <>
      <section className="dn-overlay-document" aria-label={title}>
        <div className="dn-overlay-savebar">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge variant="secondary" className="dn-authority-badge dn-authority-badge--overlay">
              <FilePenLine aria-hidden="true" />
              {t('knowledge.overlay.writable')}
            </Badge>
            <span className="text-xs font-medium">
              {t('knowledge.overlay.revision', {
                revision: loadedPage.overlay.revision,
              })}
            </span>
            <span className="text-xs text-muted-foreground">
              {t(projectionKey)}
            </span>
            {isDirty && (
              <span className="dn-overlay-dirty">
                <span aria-hidden="true">●</span>
                {t('knowledge.overlay.dirtyDraft')}
              </span>
            )}
            <span aria-live="polite" className="text-xs text-muted-foreground">
              {saveStatus === 'saved' ? (
                <>
                  <Check aria-hidden="true" className="mr-1 inline size-3.5" />
                  {t('knowledge.overlay.saved')}
                </>
              ) : null}
            </span>
          </div>
          <Button
            type="button"
            size="sm"
            disabled={!draft.title.trim() || !isDirty || busy}
            onClick={() => void save()}
          >
            {saving ? t('knowledge.overlay.saving') : t('knowledge.overlay.save')}
          </Button>
        </div>

        {saveStatus === 'conflict' && (
          <div role="alert" className="dn-overlay-alert dn-overlay-alert--conflict">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
            <span className="min-w-0 flex-1">{t('knowledge.overlay.conflict')}</span>
            <Button
              ref={reviewButtonRef}
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setReloadDialogOpen(true)}
            >
              <RefreshCw aria-hidden="true" className="mr-1.5 size-3.5" />
              {t('knowledge.overlay.reload')}
            </Button>
          </div>
        )}
        {saveStatus === 'error' && (
          <p role="alert" className="dn-overlay-alert text-destructive">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
            {t('knowledge.overlay.saveError')}
          </p>
        )}
        {reloadError && (
          <p role="alert" className="dn-overlay-alert text-destructive">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
            {t('knowledge.overlay.reloadError')}
          </p>
        )}

        <article
          ref={containerRef}
          className="grid gap-6 p-4 xl:grid-cols-[minmax(0,1fr)_13rem]"
        >
          <div className="min-w-0">{document}</div>
          <aside className="space-y-5" aria-label={t('knowledge.overlay.noteDetails')}>
            <section>
              <h3 className="text-sm font-semibold">{t('knowledge.outline')}</h3>
              {model.headings.length ? (
                <ol className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {model.headings.map((heading) => (
                    <li
                      key={`${heading.slug}-${heading.sourceFrom}`}
                      className={heading.level > 1 ? 'pl-2' : undefined}
                    >
                      <button
                        type="button"
                        className="text-left hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => onHeading(heading)}
                      >
                        {heading.text}
                      </button>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  {t('knowledge.overlay.noHeadings')}
                </p>
              )}
            </section>
            <section>
              <h3 className="text-sm font-semibold">{t('knowledge.properties')}</h3>
              {properties.length ? (
                <dl className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {properties.map(([key, value]) => (
                    <div key={key}>
                      <dt className="font-medium text-foreground">{key}</dt>
                      <dd className="break-words">{displayProperty(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  {t('knowledge.noProperties')}
                </p>
              )}
            </section>
            <section>
              <h3 className="text-sm font-semibold">{t('knowledge.tags')}</h3>
              {tags.length ? (
                <ul className="mt-2 flex flex-wrap gap-1" role="list">
                  {tags.map((tag) => (
                    <li key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      #{tag}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  {t('knowledge.noTags')}
                </p>
              )}
            </section>
            <VaultLinks
              title={t('knowledge.outgoing')}
              links={displayOutgoingLinks}
              direction="target"
              unresolvedLabel={t('knowledge.unresolved')}
              onNavigate={onNavigate}
            />
            <VaultLinks
              title={t('knowledge.backlinks')}
              links={displayBacklinks}
              direction="source"
              unresolvedLabel={t('knowledge.unresolved')}
              onNavigate={onNavigate}
            />
          </aside>
        </article>
      </section>

      <AlertDialog open={reloadDialogOpen} onOpenChange={changeReloadDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('knowledge.overlay.reloadTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('knowledge.overlay.reloadDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void reloadServer()}>
              {t('knowledge.overlay.discardAndReload')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
