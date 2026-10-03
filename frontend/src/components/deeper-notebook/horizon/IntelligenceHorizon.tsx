import Link from 'next/link'
import {
  ArrowRight,
  BookOpen,
  Database,
  FileText,
  Mic,
  Search,
  Sparkles,
} from 'lucide-react'
import * as React from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'
import { RuntimeStatusPanel } from '../runtime/RuntimeStatusPanel'
import { CommandPaletteKey } from '../shell/CommandPaletteKey'
import { FolioPage } from '../folio/FolioPage'
import { FolioSpread } from '../folio/FolioSpread'
import { FolioState } from '../folio/FolioState'

export interface HorizonNotebook {
  id: string
  name: string
  created?: string
  updated?: string
  /**
   * The page supplies this when it owns route construction. The fallback keeps
   * the view fixture-friendly without introducing a data or navigation hook.
   */
  href?: string
}

/** Read-only shape returned by the existing `/readyz` query. */
export interface HorizonReadiness {
  status: 'ready' | 'not_ready'
  checks: {
    database: 'online' | 'offline' | 'unknown'
    database_error: string | null
    migrations_applied: boolean
    migrations_pending: boolean
    migrations_error: string | null
  }
}

export interface IntelligenceHorizonProps {
  status: 'loading' | 'ready' | 'offline'
  recentNotebooks: readonly HorizonNotebook[]
  onOpenStudio(): void
  onCreateNotebook(): void
  onCreatePodcast(): void
  onAsk(): void
  notebooksLoading?: boolean
  readiness?: HorizonReadiness
  dataPath?: string
  runtimeSnapshot?: unknown
  runtimeSnapshotLoading?: boolean
  onRefreshRuntime?(): void
}

type TranslateFn = ReturnType<typeof useTranslation>['t']

function relativeTime(t: TranslateFn, iso?: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  if (diff < 60_000) return t('workspace.intelligenceHorizon.relativeJustNow')
  if (diff < 3_600_000) {
    return t('workspace.intelligenceHorizon.relativeMinutes', { count: Math.floor(diff / 60_000) })
  }
  if (diff < 86_400_000) {
    return t('workspace.intelligenceHorizon.relativeHours', { count: Math.floor(diff / 3_600_000) })
  }
  if (diff < 7 * 86_400_000) {
    return t('workspace.intelligenceHorizon.relativeDays', { count: Math.floor(diff / 86_400_000) })
  }
  return new Date(iso).toLocaleDateString()
}

function actionLinkHandler(callback: () => void) {
  return (event: React.MouseEvent<HTMLAnchorElement>) => {
    // Keep modified, middle, and auxiliary clicks native so users retain
    // open-in-new-tab/window and context-menu behavior. Ordinary primary
    // clicks still use the page-owned callback for client navigation.
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return
    }
    event.preventDefault()
    callback()
  }
}

const actionLinkClassName =
  'group flex min-h-24 flex-col items-start justify-between gap-3 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-folio-paper)] p-4 text-left transition-colors hover:border-primary/60 hover:bg-[var(--dn-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

const actionButtonClassName =
  'group flex min-h-24 flex-col items-start justify-between gap-3 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-folio-paper)] p-4 text-left transition-colors hover:border-primary/60 hover:bg-[var(--dn-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

function HorizonActions({
  onOpenStudio,
  onCreateNotebook,
  onCreatePodcast,
  onAsk,
}: Pick<
  IntelligenceHorizonProps,
  'onOpenStudio' | 'onCreateNotebook' | 'onCreatePodcast' | 'onAsk'
>) {
  const { t } = useTranslation()
  return (
    <nav
      aria-label={t('workspace.intelligenceHorizon.actionsAriaLabel')}
      data-dn-horizon-actions="true"
    >
      <Link
        href="/studio"
        aria-label={t('workspace.intelligenceHorizon.studio')}
        onClick={actionLinkHandler(onOpenStudio)}
        className={`${actionLinkClassName} border-primary/40`}
      >
        <Sparkles aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">{t('workspace.intelligenceHorizon.studio')}</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            {t('workspace.intelligenceHorizon.studioHint')}
          </span>
        </span>
      </Link>

      <button
        type="button"
        aria-label={t('workspace.intelligenceHorizon.newNotebook')}
        onClick={onCreateNotebook}
        className={actionButtonClassName}
      >
        <BookOpen aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">{t('workspace.intelligenceHorizon.newNotebook')}</span>
          <span className="mt-1 block text-xs text-muted-foreground">{t('workspace.intelligenceHorizon.newNotebookHint')}</span>
        </span>
      </button>

      <button
        type="button"
        aria-label={t('workspace.intelligenceHorizon.podcast')}
        onClick={onCreatePodcast}
        className={actionButtonClassName}
      >
        <Mic aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">{t('workspace.intelligenceHorizon.podcast')}</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            {t('workspace.intelligenceHorizon.podcastHint')}
          </span>
        </span>
      </button>

      <Link
        href="/search"
        aria-label={t('workspace.intelligenceHorizon.ask')}
        onClick={actionLinkHandler(onAsk)}
        className={actionLinkClassName}
      >
        <Search aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">{t('workspace.intelligenceHorizon.ask')}</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            {t('workspace.intelligenceHorizon.askHint')}
          </span>
        </span>
      </Link>
    </nav>
  )
}

function NotebookCollectionState() {
  const { t } = useTranslation()
  return (
    <FolioState
      kind="loading"
      title={t('workspace.intelligenceHorizon.loadingTitle')}
      description={t('workspace.intelligenceHorizon.loadingDescription')}
    />
  )
}

export function IntelligenceHorizon({
  recentNotebooks,
  onOpenStudio,
  onCreateNotebook,
  onCreatePodcast,
  onAsk,
  notebooksLoading = false,
  dataPath = '~/.deeper-notebook/',
  runtimeSnapshot,
  runtimeSnapshotLoading = false,
  onRefreshRuntime,
}: IntelligenceHorizonProps) {
  const { t } = useTranslation()
  const hasRecentNotebooks = recentNotebooks.length > 0

  return (
    <div
      data-testid="horizon-scroll-region"
      className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
    >
      <FolioPage
        eyebrow={t('workspace.intelligenceHorizon.eyebrow')}
        title="Deeper Notebook"
        subtitle={t('workspace.intelligenceHorizon.subtitle')}
        data-dn-horizon-page="true"
        className="mx-auto w-full max-w-7xl"
      >
      <div
        data-dn-horizon-cover="true"
        className="relative overflow-hidden rounded-2xl border border-[var(--dn-glass-border)] bg-[var(--dn-panel)] p-6 shadow-[var(--dn-shadow-soft)] sm:p-8"
      >
        <div className="relative max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--dn-brass)]">
            {t('workspace.intelligenceHorizon.coverEyebrow')}
          </p>
          <h2 className="mt-3 max-w-2xl text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {t('workspace.intelligenceHorizon.coverTitle')}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            {t('workspace.intelligenceHorizon.coverDescription')}
          </p>
        </div>
      </div>

      <FolioSpread
        className="mt-6"
        secondaryLabel={t('workspace.intelligenceHorizon.trustModelStatus')}
        secondary={(
          <RuntimeStatusPanel
            snapshot={runtimeSnapshot}
            isLoading={runtimeSnapshotLoading}
            onRefresh={onRefreshRuntime}
            compact
          />
        )}
        primary={
          <section aria-labelledby="horizon-today-title" className="space-y-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--dn-brass)]">
                {t('workspace.intelligenceHorizon.todayEyebrow')}
              </p>
              <h2 id="horizon-today-title" className="mt-2 text-xl font-semibold tracking-tight">
                {t('workspace.intelligenceHorizon.todayTitle')}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                {t('workspace.intelligenceHorizon.todayDescription')}
              </p>
            </div>
            <div>
              <h3 className="text-base font-semibold">{t('workspace.intelligenceHorizon.quickActions')}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{t('workspace.intelligenceHorizon.quickActionsHint')}</p>
            </div>
            <HorizonActions
              onOpenStudio={onOpenStudio}
              onCreateNotebook={onCreateNotebook}
              onCreatePodcast={onCreatePodcast}
              onAsk={onAsk}
            />
          </section>
        }
      />

      <section aria-labelledby="recent-folios-title" className="mt-6 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--dn-brass)]">
              {t('workspace.intelligenceHorizon.libraryIndex')}
            </p>
            <h2 id="recent-folios-title" className="mt-1 text-xl font-semibold tracking-tight">
              {t('workspace.intelligenceHorizon.recentFolios')}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('workspace.intelligenceHorizon.recentFoliosHint')}</p>
          </div>
          <Link
            href="/notebooks"
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {t('workspace.intelligenceHorizon.allNotebooks')}
            <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
          </Link>
        </div>

        {notebooksLoading ? (
          <NotebookCollectionState />
        ) : !hasRecentNotebooks ? (
          <FolioState
            kind="empty"
            title={t('workspace.intelligenceHorizon.emptyTitle')}
            description={t('workspace.intelligenceHorizon.emptyDescription')}
            action={
              <button
                type="button"
                onClick={onOpenStudio}
                className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {t('workspace.intelligenceHorizon.openStudio')}
              </button>
            }
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {recentNotebooks.map((notebook) => (
              <Link
                key={notebook.id}
                href={notebook.href ?? `/notebooks/${encodeURIComponent(notebook.id)}`}
                aria-label={notebook.name}
                className="group flex min-h-16 min-w-0 items-center justify-between gap-4 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-folio-paper)] px-4 py-3 transition-colors hover:border-primary/60 hover:bg-[var(--dn-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex min-w-0 items-center gap-3">
                  <BookOpen
                    aria-hidden="true"
                    className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary"
                  />
                  <span className="truncate text-sm font-medium">{notebook.name}</span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {relativeTime(t, notebook.updated ?? notebook.created)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <aside
        aria-label={t('workspace.intelligenceHorizon.shortcutsAriaLabel')}
        className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-border bg-muted/30 p-3 text-xs text-muted-foreground"
      >
        <span>
          <FileText aria-hidden="true" className="mr-1 inline h-3 w-3 align-text-bottom" />
          {t('workspace.intelligenceHorizon.tipLead')} <CommandPaletteKey /> {t('workspace.intelligenceHorizon.tipTail')}
        </span>
        <span>
          <Database aria-hidden="true" className="mr-1 inline h-3 w-3 align-text-bottom" />
          {t('workspace.intelligenceHorizon.dataLead')} <code className="rounded bg-background px-1">{dataPath}</code>.
        </span>
      </aside>
      </FolioPage>
    </div>
  )
}
