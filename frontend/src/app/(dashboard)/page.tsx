/**
 * Dashboard data and action wiring.
 *
 * IntelligenceHorizon owns the downstream presentation. This page retains the
 * existing hooks, route callbacks, and create-dialog authority so opening the
 * dashboard remains read-only and no action is invoked on mount.
 */
'use client'

import { useRouter } from 'next/navigation'

import { IntelligenceHorizon } from '@/components/deeper-notebook/horizon/IntelligenceHorizon'
import type {
  HorizonNotebook,
  HorizonReadiness,
} from '@/components/deeper-notebook/horizon/IntelligenceHorizon'
import { AppShell } from '@/components/layout/AppShell'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useSystemStatus } from '@/lib/hooks/use-system-status'

export default function DashboardPage() {
  const router = useRouter()
  const { data: notebooks, isLoading: notebooksLoading } = useNotebooks(false)
  const { data: status, isLoading: statusLoading } = useSystemStatus()
  const { openNotebookDialog, openPodcastDialog } = useCreateDialogs()

  const recentNotebooks: HorizonNotebook[] = (notebooks ?? []).slice(0, 5).map((notebook) => ({
    id: notebook.id,
    name: notebook.name,
    created: notebook.created,
    updated: notebook.updated,
    // Route construction stays at the page boundary; the child is a pure view.
    href: `/notebooks/${notebook.id}`,
  }))

  const isLoading =
    notebooksLoading ||
    statusLoading === true ||
    (statusLoading === undefined && status === undefined)
  const horizonStatus = isLoading
    ? 'loading'
    : status?.status === 'ready'
      ? 'ready'
      : 'offline'
  const readiness: HorizonReadiness | undefined = status

  return (
    <AppShell>
      <IntelligenceHorizon
        status={horizonStatus}
        recentNotebooks={recentNotebooks}
        notebooksLoading={notebooksLoading}
        readiness={readiness}
        onOpenStudio={() => router.push('/studio')}
        onCreateNotebook={openNotebookDialog}
        onCreatePodcast={openPodcastDialog}
        onAsk={() => router.push('/search')}
        dataPath="~/.deeper-notebook/"
      />
    </AppShell>
  )
}
