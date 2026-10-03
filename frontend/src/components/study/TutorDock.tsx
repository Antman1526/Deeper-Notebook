'use client'

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { useProposeStudySyllabus, useStudyPlan } from '@/lib/hooks/use-study-plans'
import { useStudyAssistantInvocation } from '@/lib/hooks/use-study-assistants'
import { STUDY_AUTHORITY_KEYS, enumLabel } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  STUDY_ASSISTANT_ROLES,
  ROLE_DEFAULT_MODES,
  TUTOR_MODES,
  modeConfig,
  type StudyAssistantCitation,
  type StudyAssistantResponse,
  type StudyAssistantRole,
  type StudyProposedAction,
  type TutorMode,
} from '@/lib/types/study-assistants'

const ROLE_LABEL_KEYS: Record<StudyAssistantRole, string> = {
  study_director: 'study.tutorDock.roles.studyDirector',
  curriculum_architect: 'study.tutorDock.roles.curriculumArchitect',
  socratic_tutor: 'study.tutorDock.roles.socraticTutor',
  concept_explainer: 'study.tutorDock.roles.conceptExplainer',
  source_guide: 'study.tutorDock.roles.sourceGuide',
  practice_coach: 'study.tutorDock.roles.practiceCoach',
  exam_coach: 'study.tutorDock.roles.examCoach',
  memory_coach: 'study.tutorDock.roles.memoryCoach',
  research_scout: 'study.tutorDock.roles.researchScout',
  project_mentor: 'study.tutorDock.roles.projectMentor',
  writing_coach: 'study.tutorDock.roles.writingCoach',
  progress_coach: 'study.tutorDock.roles.progressCoach',
}

export interface StudyVoiceTranscriptEvent {
  id: number
  text: string
}

interface TutorDockProps {
  planId: string
  sourceIds?: readonly string[]
  /** Alias used by callers that already keep selected sources separately. */
  selectedSourceIds?: readonly string[]
  unitId?: string | null
  approvedNetworkScope?: readonly string[]
  sourceOnly?: boolean
  initialMode?: TutorMode
  onCitationNavigate?: (citation: StudyAssistantCitation) => void
  voiceTranscript?: StudyVoiceTranscriptEvent | null
  onAssistantAnswer?: (answer: string) => void
}

function safeErrorMessage(error: unknown, t: (key: string) => string): string {
  const value = error as {
    response?: { data?: { detail?: { code?: string } | string } }
    message?: string
  } | null
  const detail = value?.response?.data?.detail
  const code = typeof detail === 'object' && detail ? detail.code : typeof detail === 'string' ? detail : value?.message
  if (code && /timeout/i.test(code)) return t('study.tutorDock.errors.timeout')
  if (code && /cancel/i.test(code)) return t('study.tutorDock.errors.cancelled')
  if (code && /network|web/i.test(code)) return t('study.tutorDock.errors.webUnavailable')
  if (code && /authority|scope|policy/i.test(code)) return t('study.tutorDock.errors.outsideAuthority')
  return t('study.tutorDock.errors.generic')
}

function modeLabel(mode: TutorMode, t: (key: string) => string): string {
  return t(modeConfig(mode).labelKey)
}

function citationLabel(citation: StudyAssistantCitation): string {
  const title = citation.title ?? citation.source_id
  return citation.locator ? `${title}, ${citation.locator}` : title
}

function createRequestId(): string {
  const randomUuid = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `study-assistant-request:${randomUuid}`.slice(0, 256)
}

function navigationTarget(action: StudyProposedAction, planId: string, sourceId?: string): string | null {
  const encodedPlan = encodeURIComponent(planId)
  if (action.action === 'navigate.plan') return `/study/plans/${encodedPlan}?tab=overview`
  if (action.action === 'navigate.unit' && action.unit_id) {
    return `/study/plans/${encodedPlan}?tab=learn&unit=${encodeURIComponent(action.unit_id)}`
  }
  if (action.action === 'navigate.source' && sourceId) return `/sources/${encodeURIComponent(sourceId)}`
  if (action.action === 'navigate.review') return '/study'
  return null
}

export function TutorDock({
  planId,
  sourceIds = [],
  selectedSourceIds,
  unitId = null,
  approvedNetworkScope = [],
  sourceOnly: sourceOnlyProp = false,
  initialMode = 'teach_me',
  onCitationNavigate,
  voiceTranscript = null,
  onAssistantAnswer,
}: TutorDockProps) {
  const { t } = useTranslation()
  const router = useRouter()
  const [isOpen, setIsOpen] = useState(true)
  const [mode, setMode] = useState<TutorMode>(initialMode)
  const [role, setRole] = useState<StudyAssistantRole>(modeConfig(initialMode).role)
  const [prompt, setPrompt] = useState('')
  const [webPermissionRequested, setWebPermissionRequested] = useState(false)
  const [proposal, setProposal] = useState<StudyProposedAction | null>(null)
  const [proposalError, setProposalError] = useState<string | null>(null)
  const [actionStatus, setActionStatus] = useState<string | null>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const focusAfterOpenRef = useRef(false)
  const invocation = useStudyAssistantInvocation()
  const [localResponse, setLocalResponse] = useState<StudyAssistantResponse | null>(null)
  const plan = useStudyPlan(planId)
  const proposeSyllabus = useProposeStudySyllabus()

  const config = modeConfig(mode)
  const selectedSources = useMemo(
    () => [...(selectedSourceIds ?? sourceIds)],
    [selectedSourceIds, sourceIds],
  )
  const requiresWebPermission = config.requires_web_permission || role === 'research_scout'
  const hasApprovedScope = approvedNetworkScope.length > 0
  const sourceOnly = sourceOnlyProp || config.source_only || role === 'source_guide'
  const transcriptEventId = voiceTranscript?.id
  const transcriptEventText = voiceTranscript?.text

  useEffect(() => {
    if (transcriptEventId !== undefined) setPrompt(transcriptEventText ?? '')
  }, [transcriptEventId, transcriptEventText])

  useEffect(() => {
    const response = localResponse ?? invocation.data
    if (response) onAssistantAnswer?.(response.answer)
  }, [invocation.data, localResponse, onAssistantAnswer])

  useLayoutEffect(() => {
    if (!isOpen || !focusAfterOpenRef.current) return
    focusAfterOpenRef.current = false
    toggleRef.current?.focus()
  }, [isOpen])

  const changeMode = (nextMode: TutorMode) => {
    setMode(nextMode)
    setRole(modeConfig(nextMode).role)
    setWebPermissionRequested(false)
    setActionStatus(null)
  }

  const changeRole = (nextRole: StudyAssistantRole) => {
    setRole(nextRole)
    setMode(ROLE_DEFAULT_MODES[nextRole])
    setWebPermissionRequested(false)
    setActionStatus(null)
  }

  const closeDock = () => {
    focusAfterOpenRef.current = true
    setIsOpen(false)
    queueMicrotask(() => toggleRef.current?.focus())
  }

  const openDock = () => setIsOpen(true)

  const submit = async () => {
    if (invocation.isPending || !prompt.trim()) return
    if (requiresWebPermission && !webPermissionRequested) {
      setActionStatus(t('study.tutorDock.status.permissionNeeded'))
      return
    }
    if (requiresWebPermission && !hasApprovedScope) {
      setActionStatus(t('study.tutorDock.status.scopeRequired'))
      return
    }
    setActionStatus(null)
    const networkAllowed = requiresWebPermission && webPermissionRequested
    try {
      const result = await invocation.mutateAsync({
        planId,
        role,
        input: {
          request_id: createRequestId(),
          authority: config.authority,
          prompt: prompt.trim(),
          ...(unitId ? { unit_id: unitId } : {}),
          selected_source_ids: selectedSources,
          model_route: networkAllowed ? config.model_route : 'local',
          network_allowed: networkAllowed,
          approved_network_scope: networkAllowed ? [...approvedNetworkScope] : [],
          timeout_seconds: 120,
        },
      })
      if (result) setLocalResponse(result)
    } catch {
      // The hook exposes the safe error state and retry control.
    }
  }

  const navigateCitation = (citation: StudyAssistantCitation) => {
    if (onCitationNavigate) {
      onCitationNavigate(citation)
      return
    }
    const locator = citation.locator ? `?locator=${encodeURIComponent(citation.locator)}` : ''
    router.push(`/sources/${encodeURIComponent(citation.source_id)}${locator}`)
  }

  const applyProposal = async () => {
    if (!proposal) return
    setProposalError(null)
    const target = navigationTarget(proposal, planId, selectedSources[0])
    if (target) {
      router.push(target)
      setActionStatus(t('study.tutorDock.status.opened', { label: proposal.label }))
      setProposal(null)
      return
    }
    if (proposal.action === 'plan.propose.syllabus') {
      const expectedRevision = plan.data?.version
      if (!expectedRevision) {
        setProposalError(t('study.tutorDock.proposalErrors.revisionUnavailable'))
        return
      }
      try {
        await proposeSyllabus.mutateAsync({ planId, input: { expected_revision: expectedRevision } })
        setActionStatus(t('study.tutorDock.status.syllabusRequested'))
        setProposal(null)
      } catch (error) {
        setProposalError(safeErrorMessage(error, t))
      }
      return
    }
    setProposalError(t('study.tutorDock.proposalErrors.actionUnavailable'))
  }

  return (
    <section aria-label={t('study.tutorDock.title')} className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('study.tutorDock.foregroundTutor')}</p>
          <h2 className="text-lg font-semibold">{t('study.tutorDock.subtitle')}</h2>
        </div>
        <Button
          ref={toggleRef}
          type="button"
          variant="outline"
          aria-expanded={isOpen}
          aria-controls="study-tutor-dock-panel"
          onClick={isOpen ? closeDock : openDock}
        >
          {isOpen ? t('study.tutorDock.close') : t('study.tutorDock.open')}
        </Button>
      </div>

      {isOpen ? (
        <Card id="study-tutor-dock-panel" data-state="open" className="border-primary/30 shadow-sm">
          <CardHeader className="gap-3 border-b pb-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle className="text-base">{t('study.tutorDock.title')}</CardTitle>
                <CardDescription>{t('study.tutorDock.description')}</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                {sourceOnly ? <Badge variant="outline">{t('study.tutorDock.sourceOnly')}</Badge> : null}
                <Badge variant="secondary">{t('study.tutorDock.authorityBadge', { authority: enumLabel(t, STUDY_AUTHORITY_KEYS, config.authority) })}</Badge>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm font-medium" htmlFor="tutor-role">
                {t('study.tutorDock.tutorRole')}
                <select
                  id="tutor-role"
                  aria-label={t('study.tutorDock.tutorRole')}
                  value={role}
                  onChange={(event) => changeRole(event.target.value as StudyAssistantRole)}
                  className="border-input bg-background mt-1 flex h-9 w-full rounded-md border px-3 text-sm"
                  disabled={invocation.isPending}
                >
                  {STUDY_ASSISTANT_ROLES.map((candidate) => <option key={candidate} value={candidate}>{t(ROLE_LABEL_KEYS[candidate])}</option>)}
                </select>
              </label>
              <label className="space-y-1 text-sm font-medium" htmlFor="tutor-mode">
                {t('study.tutorDock.tutorMode')}
                <select
                  id="tutor-mode"
                  aria-label={t('study.tutorDock.tutorMode')}
                  value={mode}
                  onChange={(event) => changeMode(event.target.value as TutorMode)}
                  className="border-input bg-background mt-1 flex h-9 w-full rounded-md border px-3 text-sm"
                  disabled={invocation.isPending}
                >
                  {TUTOR_MODES.map((candidate) => <option key={candidate} value={candidate}>{modeLabel(candidate, t)}</option>)}
                </select>
              </label>
            </div>
            {requiresWebPermission ? (
              // v0.8.130 — status colours from theme tokens (UI audit Phase 1)
              <div className="space-y-2 rounded-md border border-warning/40 bg-warning-soft p-3 text-sm">
                <p className="font-medium">{t('study.tutorDock.webOff')}</p>
                {!webPermissionRequested ? (
                  <Button type="button" variant="outline" onClick={() => setWebPermissionRequested(true)} disabled={invocation.isPending}>
                    {t('study.tutorDock.requestWebPermission')}
                  </Button>
                ) : (
                  <p role="status" className="text-muted-foreground">{t('study.tutorDock.webPermissionRequested')}</p>
                )}
                {!hasApprovedScope ? <p className="text-xs text-muted-foreground">{t('study.tutorDock.scopeHint')}</p> : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4 p-4">
            <label className="block space-y-1 text-sm font-medium" htmlFor="tutor-prompt">
              {t('study.tutorDock.prompt.label')}
              <Textarea
                id="tutor-prompt"
                aria-label={t('study.tutorDock.prompt.aria')}
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={t('study.tutorDock.prompt.placeholder', { mode: modeLabel(mode, t) })}
                rows={4}
                disabled={invocation.isPending}
              />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" onClick={() => void submit()} disabled={invocation.isPending || !prompt.trim()}>
                {invocation.isPending ? t('study.tutorDock.working') : t('study.tutorDock.askTutor')}
              </Button>
              <Button type="button" variant="outline" onClick={invocation.cancel} disabled={!invocation.isPending}>
                {t('study.tutorDock.cancelInvocation')}
              </Button>
              {invocation.isError ? <Button type="button" variant="outline" onClick={() => void invocation.retry()}>{t('study.tutorDock.retry')}</Button> : null}
            </div>
            {invocation.isPending ? <p role="status" className="text-sm text-muted-foreground">{t('study.tutorDock.workingStatus')}</p> : null}
            {invocation.isCancelled ? <p role="status" className="text-sm text-muted-foreground">{t('study.tutorDock.cancelledStatus')}</p> : null}
            {invocation.isError ? <p role="alert" className="text-sm text-destructive">{safeErrorMessage(invocation.error, t)}</p> : null}
            {actionStatus ? <p role="status" className="text-sm text-muted-foreground">{actionStatus}</p> : null}

            {(localResponse ?? invocation.data) ? (
              <div className="space-y-4 border-t pt-4">
                <div className="whitespace-pre-wrap text-sm leading-6">{(localResponse ?? invocation.data)?.answer}</div>
                {(localResponse ?? invocation.data)?.citations.length ? (
                  <div className="space-y-2" aria-label={t('study.tutorDock.citationsLabel')} role="region">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('study.tutorDock.evidence')}</p>
                    <div className="flex flex-wrap gap-2">
                      {(localResponse ?? invocation.data)?.citations.map((citation, index) => (
                        <Button
                          key={`${citation.source_id}-${citation.locator ?? index}`}
                          type="button"
                          variant="outline"
                          className="h-auto whitespace-normal text-left text-xs"
                          onClick={() => navigateCitation(citation)}
                        >
                          {citationLabel(citation)}
                        </Button>
                      ))}
                    </div>
                  </div>
                ) : null}
                {(localResponse ?? invocation.data)?.proposed_actions.length ? (
                  <div className="space-y-2" aria-label={t('study.tutorDock.proposalsLabel')}>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('study.tutorDock.proposedActions')}</p>
                    <div className="grid gap-2">
                      {(localResponse ?? invocation.data)?.proposed_actions.map((action) => (
                        <Button key={`${action.action}-${action.label}`} type="button" variant="outline" className="justify-start whitespace-normal text-left" onClick={() => setProposal(action)}>
                          {action.label}
                        </Button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <div data-state="closed" className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          {t('study.tutorDock.compact')}
        </div>
      )}

      <Dialog open={proposal !== null} onOpenChange={(open) => { if (!open) { setProposal(null); setProposalError(null) } }}>
        <DialogContent aria-label={t('study.tutorDock.review.title')}>
          <DialogHeader>
            <DialogTitle>{t('study.tutorDock.review.title')}</DialogTitle>
            <DialogDescription>
              {t('study.tutorDock.review.description')}
            </DialogDescription>
          </DialogHeader>
          {proposal ? (
            <div className="space-y-2 rounded-md border bg-muted/20 p-3 text-sm">
              <p className="font-medium">{proposal.label}</p>
              <p className="text-muted-foreground">{t('study.tutorDock.review.action')} <code>{proposal.action}</code></p>
              {proposal.action !== 'plan.propose.syllabus' && !navigationTarget(proposal, planId, selectedSources[0]) ? (
                <p className="text-warning-ink">{t('study.tutorDock.review.unavailable')}</p>
              ) : null}
            </div>
          ) : null}
          {proposalError ? <p role="alert" className="text-sm text-destructive">{proposalError}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => { setProposal(null); setProposalError(null) }} disabled={proposeSyllabus.isPending}>{t('common.cancel')}</Button>
            <Button type="button" onClick={() => void applyProposal()} disabled={proposeSyllabus.isPending}>
              {proposal && navigationTarget(proposal, planId, selectedSources[0]) ? t('study.tutorDock.review.openDestination') : t('study.tutorDock.review.confirmProposal')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
