import Link from 'next/link'
import * as React from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'
import { formatDate } from '@/lib/utils/date-locale'
import { RuntimeStatusPanel } from '@/components/deeper-notebook/runtime/RuntimeStatusPanel'
import { CommandPaletteKey } from '@/components/deeper-notebook/shell/CommandPaletteKey'

import type { IntelligenceHorizonProps } from '../horizon/IntelligenceHorizon'
import { StatePanel } from './StatePanel'
import { VisualCard } from './VisualCard'
import { VisualCardGrid } from './VisualCardGrid'
import { WorkspaceHero } from './WorkspaceHero'
import { WorkspacePage } from './WorkspacePage'
import { RichText } from '@/components/common/RichText'

/** The V2 home consumes the exact presentation contract of IntelligenceHorizon. */
export type WorkspaceHomeProps = IntelligenceHorizonProps

type TranslateFn = ReturnType<typeof useTranslation>['t']

function relativeTime(t: TranslateFn, language: string, iso?: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  if (diff < 60_000) return t('workspace.workspaceHome.relativeJustNow')
  if (diff < 3_600_000) {
    return t('workspace.workspaceHome.relativeMinutes', { count: Math.floor(diff / 60_000) })
  }
  if (diff < 86_400_000) {
    return t('workspace.workspaceHome.relativeHours', { count: Math.floor(diff / 3_600_000) })
  }
  if (diff < 7 * 86_400_000) {
    return t('workspace.workspaceHome.relativeDays', { count: Math.floor(diff / 86_400_000) })
  }
  return formatDate(iso, language)
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
  const { t, language } = useTranslation()
  const hasRecentNotebooks = recentNotebooks.length > 0

  return (
    <WorkspacePage
      title="Deeper Notebook"
      eyebrow={t('workspace.workspaceHome.eyebrow')}
      description={t('workspace.workspaceHome.description')}
      // v0.8.130 — Phase 3a: scopes the section spacing (workspace.css) to the home.
      className="dn-workspace-home"
      data-testid="visual-system-v2-home"
      data-dn-visual-system="v2"
    >
      <WorkspaceHero
        eyebrow={t('workspace.workspaceHome.heroEyebrow')}
        title={t('workspace.workspaceHome.heroTitle')}
        description={t('workspace.workspaceHome.heroDescription')}
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
            <p className="dn-workspace-page-eyebrow">{t('workspace.workspaceHome.todayEyebrow')}</p>
            <h2 id="workspace-actions-title" className="dn-workspace-section-title">
              {t('workspace.workspaceHome.todayTitle')}
            </h2>
            <p className="dn-workspace-section-description">
              {t('workspace.workspaceHome.todayDescription')}
            </p>
          </div>
        </div>

        <VisualCardGrid minimum="compact" role="group" aria-label={t('workspace.workspaceHome.actionsAriaLabel')}>
          <VisualCard
            title={t('workspace.workspaceHome.studio')}
            description={t('workspace.workspaceHome.studioHint')}
          >
            <ActionLink
              href="/studio"
              label={t('workspace.workspaceHome.studio')}
              onNavigate={onOpenStudio}
            />
          </VisualCard>
          <VisualCard
            title={t('workspace.workspaceHome.newNotebook')}
            description={t('workspace.workspaceHome.newNotebookHint')}
          >
            <ActionButton
              label={t('workspace.workspaceHome.newNotebook')}
              onActivate={onCreateNotebook}
            />
          </VisualCard>
          <VisualCard
            title={t('workspace.workspaceHome.podcast')}
            description={t('workspace.workspaceHome.podcastHint')}
          >
            <ActionButton
              label={t('workspace.workspaceHome.podcast')}
              onActivate={onCreatePodcast}
            />
          </VisualCard>
          <VisualCard
            title={t('workspace.workspaceHome.ask')}
            description={t('workspace.workspaceHome.askHint')}
          >
            <ActionLink
              href="/search"
              label={t('workspace.workspaceHome.ask')}
              onNavigate={onAsk}
            />
          </VisualCard>
        </VisualCardGrid>
      </section>

      <section aria-labelledby="workspace-recent-title" className="dn-workspace-section">
        <div className="dn-workspace-section-heading">
          <div>
            <p className="dn-workspace-page-eyebrow">{t('workspace.workspaceHome.libraryIndex')}</p>
            <h2 id="workspace-recent-title" className="dn-workspace-section-title">
              {t('workspace.workspaceHome.recentFolios')}
            </h2>
            <p className="dn-workspace-section-description">{t('workspace.workspaceHome.recentFoliosHint')}</p>
          </div>
          <Link href="/notebooks" className="dn-workspace-secondary-link">
            {t('workspace.workspaceHome.allNotebooks')}
          </Link>
        </div>

        {notebooksLoading ? (
          <StatePanel
            kind="loading"
            title={t('workspace.workspaceHome.loadingTitle')}
            description={t('workspace.workspaceHome.loadingDescription')}
          />
        ) : !hasRecentNotebooks ? (
          <StatePanel
            kind="empty"
            title={t('workspace.workspaceHome.emptyTitle')}
            description={t('workspace.workspaceHome.emptyDescription')}
            action={
              <button
                type="button"
                onClick={onOpenStudio}
                className="dn-visual-card-action"
              >
                {t('workspace.workspaceHome.openStudio')}
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
                  {relativeTime(t, language, notebook.updated ?? notebook.created)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <aside aria-label={t('workspace.workspaceHome.shortcutsAriaLabel')} className="dn-workspace-note">
        <span>
          <RichText text={t('workspace.workspaceHome.tip')} components={{ key: () => <CommandPaletteKey /> }} />
        </span>
        <span><RichText text={t('workspace.workspaceHome.data')} components={{ path: () => <code>{dataPath}</code> }} /></span>
      </aside>
    </WorkspacePage>
  )
}
