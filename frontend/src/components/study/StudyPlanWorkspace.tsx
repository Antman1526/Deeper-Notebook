'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo, useRef, useState } from 'react'

import { SyllabusEditor } from '@/components/study/SyllabusEditor'
import { AnkiPackagePanel } from '@/components/study/AnkiPackagePanel'
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
import { STUDY_PLAN_STATE_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { StudyPlanState } from '@/lib/types/study-plans'
import { RichText } from '@/components/common/RichText'

export const STUDY_PLAN_TABS = [
  { value: 'overview', labelKey: 'study.studyPlanWorkspace.tabs.overview' },
  { value: 'syllabus', labelKey: 'study.studyPlanWorkspace.tabs.syllabus' },
  { value: 'learn', labelKey: 'study.studyPlanWorkspace.tabs.learn' },
  { value: 'guide', labelKey: 'study.studyPlanWorkspace.tabs.guide' },
  { value: 'map', labelKey: 'study.studyPlanWorkspace.tabs.map' },
  { value: 'practice', labelKey: 'study.studyPlanWorkspace.tabs.practice' },
  { value: 'flashcards', labelKey: 'study.studyPlanWorkspace.tabs.flashcards' },
  { value: 'sources', labelKey: 'study.studyPlanWorkspace.tabs.sources' },
  { value: 'progress', labelKey: 'study.studyPlanWorkspace.tabs.progress' },
  { value: 'package', labelKey: 'study.studyPlanWorkspace.tabs.ankiPackage' },
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

function safeErrorMessage(error: unknown, t: (key: string) => string): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return t('study.studyPlanWorkspace.errors.planChanged')
  if (status === 503) return t('study.studyPlanWorkspace.errors.serviceUnavailable')
  return t('study.studyPlanWorkspace.errors.couldNotLoad')
}

function stateLabel(t: (key: string) => string, state: StudyPlanState): string {
  return enumLabel(t, STUDY_PLAN_STATE_KEYS, state, spacedEnum(state))
}

export interface StudyPlanWorkspaceProps {
  planId: string
}

export function StudyPlanWorkspace({ planId }: StudyPlanWorkspaceProps) {
  const { t } = useTranslation()
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
    if (!readiness.data) {
      return sourceCount === 1
        ? t('study.studyPlanWorkspace.sourceSummaryOne', { count: sourceCount })
        : t('study.studyPlanWorkspace.sourceSummaryOther', { count: sourceCount })
    }
    const readyCount = readiness.data.items.filter((item) => item.ready && item.fingerprint_status === 'available').length
    return t('study.studyPlanWorkspace.sourceSummaryReady', { ready: readyCount, total: readiness.data.items.length })
  }, [readiness.data, sourceCount, t])

  const proposeSyllabus = async () => {
    if (!plan.data || !canPropose) return
    setActionError(null)
    try {
      await propose.mutateAsync({ planId, input: { expected_revision: plan.data.version } })
      await Promise.all([plan.refetch(), syllabus.refetch()])
    } catch (error) {
      setActionError(safeErrorMessage(error, t))
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
    return <div role="status" className="space-y-4 rounded-lg border p-6 text-sm text-muted-foreground">{t('study.studyPlanWorkspace.loadingPlan')}</div>
  }

  if (plan.isError || !plan.data) {
    return (
      <div className="space-y-4 rounded-lg border border-destructive/40 bg-destructive/5 p-6" role="alert">
        <h2 className="text-xl font-semibold">{t('study.studyPlanWorkspace.planUnavailableTitle')}</h2>
        <p className="text-sm text-destructive">{t('study.studyPlanWorkspace.planUnavailableDescription')}</p>
        <Button type="button" variant="outline" onClick={() => void refreshAll()}>{t('study.studyPlanWorkspace.retry')}</Button>
      </div>
    )
  }

  const currentPlan = plan.data
  const tutorAvailable = ASSISTANT_PLAN_STATES.has(currentPlan.state)
    && currentPlan.approved_syllabus_version !== null
  const syllabusContent = syllabus.isLoading ? (
    <p role="status" className="rounded-lg border p-6 text-sm text-muted-foreground">{t('study.studyPlanWorkspace.loadingSyllabus')}</p>
  ) : syllabus.isError ? (
    <div role="alert" className="space-y-3 rounded-lg border border-destructive/40 bg-destructive/5 p-6">
      <p className="text-sm text-destructive">{t('study.studyPlanWorkspace.syllabusLoadError')}</p>
      <Button type="button" variant="outline" onClick={() => void refreshAll()}>{t('study.studyPlanWorkspace.retrySyllabus')}</Button>
    </div>
  ) : !syllabus.data ? (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('study.studyPlanWorkspace.noProposalTitle')}</CardTitle>
        <CardDescription>
          {t('study.studyPlanWorkspace.noProposalDescription')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!canPropose ? <p className="text-sm text-muted-foreground">{t('study.studyPlanWorkspace.proposalAfterAnalysis')}</p> : null}
        <Button type="button" onClick={() => void proposeSyllabus()} disabled={!canPropose || propose.isPending}>
          {propose.isPending ? t('study.studyPlanWorkspace.preparingProposal') : t('study.studyPlanWorkspace.proposeSyllabus')}
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
          <Link href="/study" className="text-sm text-muted-foreground underline-offset-4 hover:underline">{t('study.studyPlanWorkspace.backToStudy')}</Link>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold tracking-tight">{currentPlan.goal}</h2>
            <Badge variant={currentPlan.state === 'approved' ? 'default' : 'outline'}>{stateLabel(t, currentPlan.state)}</Badge>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            {t('study.studyPlanWorkspace.planMeta', { level: currentPlan.starting_level, sources: sourceSummary, version: currentPlan.version })}
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => void refreshAll()}>{t('common.refresh')}</Button>
      </header>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-5">
        <TabsList aria-label={t('study.studyPlanWorkspace.sectionsLabel')} data-dn-horizontal-scroll="study-tabs" className="w-full justify-start overflow-x-auto">
          {STUDY_PLAN_TABS.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              onClick={() => handleTabChange(tab.value)}
            >
              {t(tab.labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('study.studyPlanWorkspace.overview.title')}</CardTitle>
              <CardDescription>{t('study.studyPlanWorkspace.overview.description')}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <div><p className="text-xs uppercase tracking-wide text-muted-foreground">{t('study.studyPlanWorkspace.overview.startingLevel')}</p><p className="mt-1 font-medium">{currentPlan.starting_level}</p></div>
              <div><p className="text-xs uppercase tracking-wide text-muted-foreground">{t('study.studyPlanWorkspace.overview.linkedSources')}</p><p className="mt-1 font-medium">{sourceCount}</p></div>
              <div><p className="text-xs uppercase tracking-wide text-muted-foreground">{t('study.studyPlanWorkspace.overview.approvedVersion')}</p><p className="mt-1 font-medium">{currentPlan.approved_syllabus_version ?? t('study.studyPlanWorkspace.overview.notApproved')}</p></div>
            </CardContent>
          </Card>
          <p className="text-sm text-muted-foreground"><RichText text={t('study.studyPlanWorkspace.overview.existingCards')} components={{ link: (children) => <Link href="/study" className="underline underline-offset-4">{children}</Link> }} /></p>
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
                <CardTitle>{t('study.studyPlanWorkspace.learnUnavailableTitle')}</CardTitle>
                <CardDescription>
                  {t('study.studyPlanWorkspace.learnUnavailableDescription')}
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

        <TabsContent value="package" className="space-y-4">
          <AnkiPackagePanel planId={planId} lifecycleState={currentPlan.state} />
        </TabsContent>

        {(['guide', 'map', 'practice', 'flashcards', 'sources'] as const).map((tab) => (
          <TabsContent key={tab} value={tab} className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>{t(STUDY_PLAN_TABS.find((entry) => entry.value === tab)?.labelKey ?? 'study.studyPlanWorkspace.tabs.overview')}</CardTitle>
                <CardDescription>{t('study.studyPlanWorkspace.reserved.description')}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{t('study.studyPlanWorkspace.reserved.body')}</p>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
