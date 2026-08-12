'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo, useRef, useState } from 'react'

import { SyllabusEditor } from '@/components/study/SyllabusEditor'
import { StudyLearningSession } from '@/components/study/StudyLearningSession'
import { StudyProgressPanel } from '@/components/study/StudyProgressPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  useProposeStudySyllabus,
  useDecideStudyProgress,
  useStudyPlan,
  useStudyPlanProgress,
  useStudyPlanReadiness,
  useStudySyllabus,
} from '@/lib/hooks/use-study-plans'
import type { StudyPlanState } from '@/lib/types/study-plans'

export const STUDY_PLAN_TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'syllabus', label: 'Syllabus' },
  { value: 'learn', label: 'Learn' },
  { value: 'guide', label: 'Guide' },
  { value: 'map', label: 'Map' },
  { value: 'practice', label: 'Practice' },
  { value: 'flashcards', label: 'Flashcards' },
  { value: 'sources', label: 'Sources' },
  { value: 'progress', label: 'Progress' },
] as const

export type StudyPlanTab = typeof STUDY_PLAN_TABS[number]['value']

const ASSISTANT_PLAN_STATES = new Set<StudyPlanState>([
  'approved',
  'generating',
  'active',
  'completed',
])

export function normalizeStudyPlanTab(value: string | null | undefined): StudyPlanTab {
  return STUDY_PLAN_TABS.some((tab) => tab.value === value)
    ? value as StudyPlanTab
    : 'overview'
}

function safeErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return 'This plan changed elsewhere. Refresh the workspace before continuing.'
  if (status === 503) return 'The syllabus service is temporarily unavailable. Try again shortly.'
  return 'The syllabus could not be loaded. Nothing was changed; try again.'
}

function stateLabel(state: StudyPlanState): string {
  return state.replaceAll('_', ' ')
}

export interface StudyPlanWorkspaceProps {
  planId: string
}

export function StudyPlanWorkspace({ planId }: StudyPlanWorkspaceProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const activeTab = normalizeStudyPlanTab(searchParams.get('tab'))
  const navigationTabRef = useRef<string | null>(null)
  const plan = useStudyPlan(planId)
  const syllabus = useStudySyllabus(planId)
  const readiness = useStudyPlanReadiness(planId)
  const progress = useStudyPlanProgress(planId)
  const propose = useProposeStudySyllabus()
  const decideProgress = useDecideStudyProgress()
  const [actionError, setActionError] = useState<string | null>(null)

  const refreshAll = async () => {
    await Promise.all([plan.refetch(), syllabus.refetch(), readiness.refetch(), progress.refetch()])
  }

  const handleTabChange = (value: string) => {
    const nextTab = normalizeStudyPlanTab(value)
    if (navigationTabRef.current === nextTab) return
    navigationTabRef.current = nextTab
    router.replace(`/study/plans/${encodeURIComponent(planId)}?tab=${nextTab}`, { scroll: false })
    queueMicrotask(() => {
      navigationTabRef.current = null
    })
  }

  const sourceCount = plan.data?.source_links.length ?? 0
  const allSourcesReady = readiness.data
    ? readiness.data.items.length === sourceCount && readiness.data.items.every((item) => item.ready && item.reason === 'ready' && item.fingerprint_status === 'available')
    : false
  const canPropose = plan.data?.state === 'analyzing_sources' && !readiness.isLoading && !readiness.isError && readiness.data?.ready === true && allSourcesReady
  const sourceSummary = useMemo(() => {
    if (!readiness.data) return `${sourceCount} linked ${sourceCount === 1 ? 'source' : 'sources'}`
    const readyCount = readiness.data.items.filter((item) => item.ready && item.fingerprint_status === 'available').length
    return `${readyCount} of ${readiness.data.items.length} sources ready`
  }, [readiness.data, sourceCount])

  const proposeSyllabus = async () => {
    if (!plan.data || !canPropose) return
    setActionError(null)
    try {
      await propose.mutateAsync({ planId, input: { expected_revision: plan.data.version } })
      await Promise.all([plan.refetch(), syllabus.refetch()])
    } catch (error) {
      setActionError(safeErrorMessage(error))
    }
  }

  const acceptProgress = async (proposalId: string, requestId: string) => {
    if (!plan.data) return
    await decideProgress.mutateAsync({
      planId,
      input: {
        proposal_id: proposalId,
        decision: 'accepted',
        request_id: requestId,
        expected_revision: plan.data.version,
      },
    })
  }

  const dismissProgress = async (proposalId: string, requestId: string) => {
    await decideProgress.mutateAsync({
      planId,
      input: { proposal_id: proposalId, decision: 'dismissed', request_id: requestId },
    })
  }

  if (plan.isLoading) {
    return <div role="status" className="space-y-4 rounded-lg border p-6 text-sm text-muted-foreground">Loading study plan…</div>
  }

  if (plan.isError || !plan.data) {
    return (
      <div className="space-y-4 rounded-lg border border-destructive/40 bg-destructive/5 p-6" role="alert">
        <h1 className="text-xl font-semibold">Study plan unavailable</h1>
        <p className="text-sm text-destructive">This plan could not be loaded. Your existing study cards and sources are unchanged.</p>
        <Button type="button" variant="outline" onClick={() => void refreshAll()}>Retry</Button>
      </div>
    )
  }

  const currentPlan = plan.data
  const tutorAvailable = ASSISTANT_PLAN_STATES.has(currentPlan.state)
    && currentPlan.approved_syllabus_version !== null
  const syllabusContent = syllabus.isLoading ? (
    <p role="status" className="rounded-lg border p-6 text-sm text-muted-foreground">Loading proposed syllabus…</p>
  ) : syllabus.isError ? (
    <div role="alert" className="space-y-3 rounded-lg border border-destructive/40 bg-destructive/5 p-6">
      <p className="text-sm text-destructive">The proposed syllabus could not be loaded. No version was changed.</p>
      <Button type="button" variant="outline" onClick={() => void refreshAll()}>Retry syllabus</Button>
    </div>
  ) : !syllabus.data ? (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">No syllabus proposal yet</CardTitle>
        <CardDescription>
          Link and verify every source before proposing a typed syllabus. The server keeps each proposal immutable.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!canPropose ? <p className="text-sm text-muted-foreground">Syllabus proposal is available after source analysis reports every linked source ready.</p> : null}
        <Button type="button" onClick={() => void proposeSyllabus()} disabled={!canPropose || propose.isPending}>
          {propose.isPending ? 'Preparing proposal…' : 'Propose syllabus'}
        </Button>
        {actionError ? <p role="alert" className="text-sm text-destructive">{actionError}</p> : null}
      </CardContent>
    </Card>
  ) : (
    <SyllabusEditor
      plan={currentPlan}
      syllabus={syllabus.data}
      readiness={readiness.data}
      readinessLoading={readiness.isLoading}
      readinessError={readiness.isError}
      onRefresh={refreshAll}
    />
  )

  return (
    <div data-testid={`study-plan-workspace-${planId}`} className="space-y-6">
      <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <Link href="/study" className="text-sm text-muted-foreground underline-offset-4 hover:underline">Back to Study</Link>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{currentPlan.goal}</h1>
            <Badge variant={currentPlan.state === 'approved' ? 'default' : 'outline'}>{stateLabel(currentPlan.state)}</Badge>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            {currentPlan.starting_level} · {sourceSummary} · Revision {currentPlan.version}
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => void refreshAll()}>Refresh</Button>
      </header>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-5">
        <TabsList aria-label="Study plan sections" className="w-full justify-start overflow-x-auto">
          {STUDY_PLAN_TABS.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              onClick={() => handleTabChange(tab.value)}
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Plan overview</CardTitle>
              <CardDescription>Keep this goal and its source boundary visible while the plan moves through review.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Starting level</p><p className="mt-1 font-medium">{currentPlan.starting_level}</p></div>
              <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Linked sources</p><p className="mt-1 font-medium">{sourceCount}</p></div>
              <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Approved version</p><p className="mt-1 font-medium">{currentPlan.approved_syllabus_version ?? 'Not approved'}</p></div>
            </CardContent>
          </Card>
          <p className="text-sm text-muted-foreground">Your existing review cards remain available on the <Link href="/study" className="underline underline-offset-4">Study home</Link>.</p>
        </TabsContent>

        <TabsContent value="syllabus" className="space-y-4">{syllabusContent}</TabsContent>

        <TabsContent value="learn" className="space-y-4">
          {tutorAvailable ? (
            <StudyLearningSession
              planId={planId}
              sourceIds={currentPlan.source_links.map((link) => link.source_id)}
              approvedNetworkScope={currentPlan.preferences?.network_allowed
                ? currentPlan.preferences.approved_network_scope
                : []}
            />
          ) : (
            <Card role="status" aria-live="polite">
              <CardHeader>
                <CardTitle>Learning session unavailable</CardTitle>
                <CardDescription>
                  Tutor unavailable until the syllabus is approved. This plan is still being prepared or archived, so no learning session can start yet.
                </CardDescription>
              </CardHeader>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="progress" className="space-y-4">
          <StudyProgressPanel
            state={progress.isLoading ? 'loading' : progress.isError ? 'error' : progress.data ? 'ready' : 'empty'}
            projection={progress.data}
            onRetry={() => void progress.refetch()}
            onAccept={acceptProgress}
            onDismiss={dismissProgress}
          />
        </TabsContent>

        {(['guide', 'map', 'practice', 'flashcards', 'sources'] as const).map((tab) => (
          <TabsContent key={tab} value={tab} className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>{STUDY_PLAN_TABS.find((entry) => entry.value === tab)?.label}</CardTitle>
                <CardDescription>This workspace section will use the approved syllabus and source boundary.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">This section is reserved for a later Study Workbench stage. No downstream artifact has been generated.</p>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
