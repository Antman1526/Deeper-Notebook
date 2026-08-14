import Link from 'next/link'
import * as React from 'react'

import { RuntimeStatusPanel } from '@/components/deeper-notebook/runtime/RuntimeStatusPanel'

import type { IntelligenceHorizonProps } from '../horizon/IntelligenceHorizon'
import { StatePanel } from './StatePanel'
import { VisualCard } from './VisualCard'
import { VisualCardGrid } from './VisualCardGrid'
import { WorkspaceHero } from './WorkspaceHero'
import { WorkspacePage } from './WorkspacePage'

/** The V2 home consumes the exact presentation contract of IntelligenceHorizon. */
export type WorkspaceHomeProps = IntelligenceHorizonProps

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

function actionLinkHandler(callback: () => void) {
  return (event: React.MouseEvent<HTMLAnchorElement>) => {
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

function ActionLink({
  href,
  label,
  onNavigate,
}: {
  href: string
  label: string
  onNavigate(): void
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      onClick={actionLinkHandler(onNavigate)}
      className="dn-visual-card-action"
    >
      <span>{label}</span>
    </Link>
  )
}

function ActionButton({
  label,
  onActivate,
}: {
  label: string
  onActivate(): void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onActivate}
      className="dn-visual-card-action"
    >
      <span>{label}</span>
    </button>
  )
}

export function WorkspaceHome({
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
}: WorkspaceHomeProps) {
  const hasRecentNotebooks = recentNotebooks.length > 0

  return (
    <WorkspacePage
      title="Deeper Notebook"
      eyebrow="Intelligence workspace"
      description="Think further with every source in one quiet, local-first desk."
      data-testid="visual-system-v2-home"
      data-dn-visual-system="v2"
    >
      <WorkspaceHero
        eyebrow="Working desk"
        title="Continue the question that matters today."
        description="Your recent folios, safe runtime signals, and next actions stay in one clear spread—ready when you are."
      />

      <RuntimeStatusPanel
        snapshot={runtimeSnapshot}
        isLoading={runtimeSnapshotLoading}
        onRefresh={onRefreshRuntime}
        compact
      />

      <section aria-labelledby="workspace-actions-title" className="dn-workspace-section">
        <div className="dn-workspace-section-heading">
          <div>
            <p className="dn-workspace-page-eyebrow">Today</p>
            <h2 id="workspace-actions-title" className="dn-workspace-section-title">
              Open a working spread
            </h2>
            <p className="dn-workspace-section-description">
              Start with a source, a notebook, a grounded question, or an explicitly reviewed podcast brief.
            </p>
          </div>
        </div>

        <VisualCardGrid minimum="compact" aria-label="Workspace actions">
          <VisualCard
            title="Studio"
            description="Drop files into a notebook or podcast brief."
          >
            <ActionLink
              href="/studio"
              label="Studio"
              onNavigate={onOpenStudio}
            />
          </VisualCard>
          <VisualCard
            title="New Notebook"
            description="Start an empty, local canvas."
          >
            <ActionButton
              label="New Notebook"
              onActivate={onCreateNotebook}
            />
          </VisualCard>
          <VisualCard
            title="Podcast"
            description="Generate a reviewed listening brief from sources."
          >
            <ActionButton
              label="Podcast"
              onActivate={onCreatePodcast}
            />
          </VisualCard>
          <VisualCard
            title="Ask"
            description="Search and synthesize from your evidence."
          >
            <ActionLink
              href="/search"
              label="Ask"
              onNavigate={onAsk}
            />
          </VisualCard>
        </VisualCardGrid>
      </section>

      <section aria-labelledby="workspace-recent-title" className="dn-workspace-section">
        <div className="dn-workspace-section-heading">
          <div>
            <p className="dn-workspace-page-eyebrow">Library index</p>
            <h2 id="workspace-recent-title" className="dn-workspace-section-title">
              Recent folios
            </h2>
            <p className="dn-workspace-section-description">Pick up where you left off.</p>
          </div>
          <Link href="/notebooks" className="dn-workspace-secondary-link">
            All notebooks
          </Link>
        </div>

        {notebooksLoading ? (
          <StatePanel
            kind="loading"
            title="Loading your notebook desk"
            description="Checking local notebooks and runtime readiness. Your workspace stays untouched while it loads."
          />
        ) : !hasRecentNotebooks ? (
          <StatePanel
            kind="empty"
            title="Your notebook is ready to begin"
            description="No notebooks yet. Drop a PDF into Studio to start your first."
            action={
              <button
                type="button"
                onClick={onOpenStudio}
                className="dn-visual-card-action"
              >
                Open Studio
              </button>
            }
          />
        ) : (
          <div className="dn-workspace-notebook-list">
            {recentNotebooks.map((notebook) => (
              <Link
                key={notebook.id}
                href={notebook.href ?? `/notebooks/${encodeURIComponent(notebook.id)}`}
                aria-label={notebook.name}
                className="dn-workspace-notebook-link"
              >
                <span className="dn-workspace-notebook-name">{notebook.name}</span>
                <span className="dn-workspace-notebook-time">
                  {relativeTime(notebook.updated ?? notebook.created)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <aside aria-label="Notebook shortcuts and data path" className="dn-workspace-note">
        <span>
          Tip: hit <kbd>⌘K</kbd> / <kbd>Ctrl+K</kbd> from anywhere to jump to a notebook, source, or action.
        </span>
        <span>All data lives in <code>{dataPath}</code>.</span>
      </aside>
    </WorkspacePage>
  )
}
