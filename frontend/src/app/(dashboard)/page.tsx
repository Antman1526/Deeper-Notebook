/**
 * Dashboard data and action wiring.
 *
 * IntelligenceHorizon owns the downstream presentation. This page retains the
 * existing hooks, route callbacks, and create-dialog authority so opening the
 * dashboard remains read-only and no action is invoked on mount.
 */
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { IntelligenceHorizon } from '@/components/deeper-notebook/horizon/IntelligenceHorizon'
import type { HorizonNotebook } from '@/components/deeper-notebook/horizon/IntelligenceHorizon'
import { WorkspaceHome } from '@/components/deeper-notebook/workspace/WorkspaceHome'
import { getConfig } from '@/lib/config'
import { isVisualSystemV2Enabled } from '@/lib/features'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { UNKNOWN_RUNTIME_SNAPSHOT } from '@/lib/api/runtime'
import { useRuntimeSnapshot } from '@/lib/hooks/use-runtime-snapshot'

export default function DashboardPage() {
  const router = useRouter()
  const { data: notebooks, isLoading: notebooksLoading } = useNotebooks(false)
  const runtime = useRuntimeSnapshot()
  const { openNotebookDialog, openPodcastDialog } = useCreateDialogs()
  // v0.8.130 — the tip named ~/.deeper-notebook/ whatever the real folder was. The
  // default stays until the backend reports the folder, and if it never does.
  const [dataPath, setDataPath] = useState('~/.deeper-notebook/')
  useEffect(() => {
    let current = true
    getConfig()
      .then((config) => { if (current && config.dataPath) setDataPath(config.dataPath) })
      .catch(() => {})
    return () => { current = false }
  }, [])

  const recentNotebooks: HorizonNotebook[] = (notebooks ?? []).slice(0, 5).map((notebook) => ({
    id: notebook.id,
    name: notebook.name,
    created: notebook.created,
    updated: notebook.updated,
    // Route construction stays at the page boundary; the child is a pure view.
    href: `/notebooks/${notebook.id}`,
  }))

  const runtimeSnapshot = runtime.data ?? UNKNOWN_RUNTIME_SNAPSHOT
  const horizonStatus: 'loading' | 'ready' | 'offline' =
    runtime.isLoading
    ? 'loading'
    : runtimeSnapshot.status === 'ready'
      ? 'ready'
      : 'offline'

  const presentationProps = {
    status: horizonStatus,
    recentNotebooks,
    notebooksLoading,
    runtimeSnapshot,
    runtimeSnapshotLoading: runtime.isLoading,
    onRefreshRuntime: () => void runtime.refetch(),
    onOpenStudio: () => router.push('/studio'),
    onCreateNotebook: openNotebookDialog,
    onCreatePodcast: openPodcastDialog,
    onAsk: () => router.push('/search'),
    dataPath,
  }
  const Presentation = isVisualSystemV2Enabled() ? WorkspaceHome : IntelligenceHorizon

  return (
    <>
      <Presentation {...presentationProps} />
    </>
  )
}
