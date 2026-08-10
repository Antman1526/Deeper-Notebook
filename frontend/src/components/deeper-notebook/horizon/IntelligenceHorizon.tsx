import Link from 'next/link'
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  Database,
  FileText,
  Mic,
  Search,
  Sparkles,
} from 'lucide-react'
import * as React from 'react'

import { EvidenceInsert } from '../folio/EvidenceInsert'
import { FolioPage } from '../folio/FolioPage'
import { FolioSpread } from '../folio/FolioSpread'
import { FolioState } from '../folio/FolioState'
import { MarginNote } from '../folio/MarginNote'

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
}

type StatusKind = 'ready' | 'loading' | 'offline'
type ReadinessState = 'ready' | 'pending' | 'offline' | 'unknown'

function relativeTime(iso?: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} min ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} hr ago`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} d ago`
  return new Date(iso).toLocaleDateString()
}

function readinessLabel(state: ReadinessState): string {
  return state
}

function StatusRow({
  label,
  state,
  detail,
}: {
  label: string
  state: ReadinessState
  detail?: string | null
}) {
  const icon =
    state === 'ready' ? (
      <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-success" />
    ) : state === 'pending' ? (
      <CircleAlert aria-hidden="true" className="h-4 w-4 text-warning" />
    ) : state === 'offline' ? (
      <CircleAlert aria-hidden="true" className="h-4 w-4 text-destructive" />
    ) : (
      <CircleDashed aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
    )

  return (
    <div className="flex items-center justify-between gap-3 py-2 text-sm">
      <div className="flex items-center gap-2">
        {icon}
        <span>{label}</span>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-right">
        <span className="text-xs text-muted-foreground">{readinessLabel(state)}</span>
        {detail ? <span className="text-xs text-muted-foreground">{detail}</span> : null}
      </div>
    </div>
  )
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
  return (
    <nav aria-label="Horizon actions" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Link
        href="/studio"
        aria-label="Studio"
        onClick={actionLinkHandler(onOpenStudio)}
        className={`${actionLinkClassName} border-primary/40`}
      >
        <Sparkles aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">Studio</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Drop files → notebook or podcast
          </span>
        </span>
      </Link>

      <button
        type="button"
        aria-label="New Notebook"
        onClick={onCreateNotebook}
        className={actionButtonClassName}
      >
        <BookOpen aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">New Notebook</span>
          <span className="mt-1 block text-xs text-muted-foreground">Empty canvas</span>
        </span>
      </button>

      <button
        type="button"
        aria-label="Podcast"
        onClick={onCreatePodcast}
        className={actionButtonClassName}
      >
        <Mic aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">Podcast</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Generate from sources
          </span>
        </span>
      </button>

      <Link
        href="/search"
        aria-label="Ask"
        onClick={actionLinkHandler(onAsk)}
        className={actionLinkClassName}
      >
        <Search aria-hidden="true" className="h-5 w-5 text-primary" />
        <span>
          <span className="block text-sm font-semibold">Ask</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Search + synthesize
          </span>
        </span>
      </Link>
    </nav>
  )
}

function StatusMargin({
  status,
  readiness,
}: {
  status: StatusKind
  readiness?: HorizonReadiness
}) {
  const apiState: ReadinessState = readiness ? 'ready' : 'unknown'
  const databaseState: ReadinessState = readiness
    ? readiness.checks.database === 'online'
      ? 'ready'
      : readiness.checks.database === 'offline'
        ? 'offline'
        : 'unknown'
    : 'unknown'
  const migrationsState: ReadinessState = readiness
    ? readiness.checks.migrations_applied
      ? 'ready'
      : readiness.checks.migrations_pending
        ? 'pending'
        : readiness.checks.migrations_error
          ? 'offline'
          : 'unknown'
    : 'unknown'
  const databaseDetail = readiness?.checks.database_error
  const migrationsDetail = readiness
    ? readiness.checks.migrations_error ?? (readiness.checks.migrations_pending ? 'pending' : null)
    : null

  return (
    <MarginNote label="Trust and model status">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">Trust and model status</h2>
        <span className="rounded-full border border-[var(--dn-paper-edge)] px-2 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {status === 'ready' ? 'Ready' : status === 'offline' ? 'Offline' : 'Loading'}
        </span>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        Local readiness stays visible before any notebook, source, or production action.
      </p>
      {status !== 'ready' ? (
        <p
          role="status"
          aria-label={`Runtime ${status}`}
          className="text-xs font-medium text-muted-foreground"
        >
          Runtime {status}
        </p>
      ) : null}
      <div>
        <h3 className="text-sm font-semibold">System status</h3>
        <p className="mt-1 text-xs text-muted-foreground">Updated every 30 s from /readyz</p>
      </div>
      <div className="divide-y divide-border/70">
        <StatusRow label="API" state={apiState} />
        <StatusRow label="Database" state={databaseState} detail={databaseDetail} />
        <StatusRow label="Migrations" state={migrationsState} detail={migrationsDetail} />
      </div>
      <EvidenceInsert label="Model route" className="border-0 bg-transparent p-0">
        <p className="text-xs leading-5 text-muted-foreground">
          Local-first routing remains unchanged until you explicitly choose an action.
        </p>
      </EvidenceInsert>
    </MarginNote>
  )
}

function NotebookCollectionState() {
  return (
    <FolioState
      kind="loading"
      title="Loading your notebook desk"
      description="Checking local notebooks and runtime readiness. Your workspace stays untouched while it loads."
    />
  )
}

export function IntelligenceHorizon({
  status,
  recentNotebooks,
  onOpenStudio,
  onCreateNotebook,
  onCreatePodcast,
  onAsk,
  notebooksLoading = false,
  readiness,
  dataPath = '~/.deeper-notebook/',
}: IntelligenceHorizonProps) {
  const hasRecentNotebooks = recentNotebooks.length > 0

  return (
    <div
      data-testid="horizon-scroll-region"
      className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
    >
      <FolioPage
        eyebrow="Intelligence Horizon"
        title="Deeper Notebook"
        subtitle="Think further with every source"
        className="mx-auto w-full max-w-7xl"
      >
      <div
        data-dn-horizon-cover="true"
        className="relative overflow-hidden rounded-2xl border border-[var(--dn-glass-border)] bg-[var(--dn-panel)] p-6 shadow-[var(--dn-shadow-soft)] sm:p-8"
      >
        <div className="relative max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--dn-brass)]">
            Notebook cover · working desk
          </p>
          <h2 className="mt-3 max-w-2xl text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Continue the question that matters today.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            Your recent folios, safe runtime signals, and next actions stay in one quiet
            spread—ready when you are.
          </p>
        </div>
      </div>

      <FolioSpread
        className="mt-6"
        secondaryLabel="Trust and model status"
        secondary={<StatusMargin status={status} readiness={readiness} />}
        primary={
          <section aria-labelledby="horizon-today-title" className="space-y-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--dn-brass)]">
                Today
              </p>
              <h2 id="horizon-today-title" className="mt-2 text-xl font-semibold tracking-tight">
                Open a working spread
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                Start with a source, a notebook, a grounded question, or an explicitly
                reviewed podcast brief.
              </p>
            </div>
            <div>
              <h3 className="text-base font-semibold">Quick actions</h3>
              <p className="mt-1 text-sm text-muted-foreground">Start something new</p>
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
              Library index
            </p>
            <h2 id="recent-folios-title" className="mt-1 text-xl font-semibold tracking-tight">
              Recent folios
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">Pick up where you left off</p>
          </div>
          <Link
            href="/notebooks"
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            All notebooks
            <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
          </Link>
        </div>

        {notebooksLoading ? (
          <NotebookCollectionState />
        ) : !hasRecentNotebooks ? (
          <FolioState
            kind="empty"
            title="Your notebook is ready to begin"
            description="No notebooks yet. Drop a PDF into Studio to start your first."
            action={
              <button
                type="button"
                onClick={onOpenStudio}
                className="inline-flex min-h-11 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Open Studio
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
                className="group flex min-h-16 items-center justify-between gap-4 rounded-xl border border-[var(--dn-paper-edge)] bg-[var(--dn-folio-paper)] px-4 py-3 transition-colors hover:border-primary/60 hover:bg-[var(--dn-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex min-w-0 items-center gap-3">
                  <BookOpen
                    aria-hidden="true"
                    className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary"
                  />
                  <span className="truncate text-sm font-medium">{notebook.name}</span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {relativeTime(notebook.updated ?? notebook.created)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <aside
        aria-label="Notebook shortcuts and data path"
        className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-border bg-muted/30 p-3 text-xs text-muted-foreground"
      >
        <span>
          <FileText aria-hidden="true" className="mr-1 inline h-3 w-3 align-text-bottom" />
          Tip: hit <kbd className="rounded border bg-background px-1 font-mono">⌘K</kbd>{' '}
          / <kbd className="rounded border bg-background px-1 font-mono">Ctrl+K</kbd> from
          anywhere to jump to a notebook, source, or action.
        </span>
        <span>
          <Database aria-hidden="true" className="mr-1 inline h-3 w-3 align-text-bottom" />
          All data lives in <code className="rounded bg-background px-1">{dataPath}</code>.
        </span>
      </aside>
      </FolioPage>
    </div>
  )
}
