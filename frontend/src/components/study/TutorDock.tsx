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

const ROLE_LABELS: Record<StudyAssistantRole, string> = {
  study_director: 'Study Director',
  curriculum_architect: 'Curriculum Architect',
  socratic_tutor: 'Socratic Tutor',
  concept_explainer: 'Concept Explainer',
  source_guide: 'Source Guide',
  practice_coach: 'Practice Coach',
  exam_coach: 'Exam Coach',
  memory_coach: 'Memory Coach',
  research_scout: 'Research Scout',
  project_mentor: 'Project Mentor',
  writing_coach: 'Writing Coach',
  progress_coach: 'Progress Coach',
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
  voiceTranscript?: string | null
  onAssistantAnswer?: (answer: string) => void
}

function safeErrorMessage(error: unknown): string {
  const value = error as {
    response?: { data?: { detail?: { code?: string } | string } }
    message?: string
  } | null
  const detail = value?.response?.data?.detail
  const code = typeof detail === 'object' && detail ? detail.code : typeof detail === 'string' ? detail : value?.message
  if (code && /timeout/i.test(code)) return 'The tutor timed out before completing. Retry the same request.'
  if (code && /cancel/i.test(code)) return 'Tutor invocation cancelled.'
  if (code && /network|web/i.test(code)) return 'Web research is unavailable for this request. Request permission and try again.'
  if (code && /authority|scope|policy/i.test(code)) return 'This tutor request is outside the approved study authority.'
  return 'The tutor could not complete this request. Nothing was changed; try again.'
}

function modeLabel(mode: TutorMode): string {
  return modeConfig(mode).label
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

  useEffect(() => {
    if (voiceTranscript !== null) setPrompt(voiceTranscript)
  }, [voiceTranscript])

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
      setActionStatus('Request web research permission before using this mode.')
      return
    }
    if (requiresWebPermission && !hasApprovedScope) {
      setActionStatus('A plan-approved HTTPS scope is required before web research can run.')
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
      setActionStatus(`Opened ${proposal.label}.`)
      setProposal(null)
      return
    }
    if (proposal.action === 'plan.propose.syllabus') {
      const expectedRevision = plan.data?.version
      if (!expectedRevision) {
        setProposalError('The current plan revision is unavailable. Refresh before confirming this proposal.')
        return
      }
      try {
        await proposeSyllabus.mutateAsync({ planId, input: { expected_revision: expectedRevision } })
        setActionStatus('Syllabus proposal requested and accepted by the plan service.')
        setProposal(null)
      } catch (error) {
        setProposalError(safeErrorMessage(error))
      }
      return
    }
    setProposalError('This proposed action is unavailable in this Study Workbench stage. Nothing was changed.')
  }

  return (
    <section aria-label="Tutor dock" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Foreground tutor</p>
          <h2 className="text-lg font-semibold">One source-aware learning conversation</h2>
        </div>
        <Button
          ref={toggleRef}
          type="button"
          variant="outline"
          aria-expanded={isOpen}
          aria-controls="study-tutor-dock-panel"
          onClick={isOpen ? closeDock : openDock}
        >
          {isOpen ? 'Close tutor dock' : 'Open tutor dock'}
        </Button>
      </div>

      {isOpen ? (
        <Card id="study-tutor-dock-panel" data-state="open" className="border-primary/30 shadow-sm">
          <CardHeader className="gap-3 border-b pb-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle className="text-base">Tutor dock</CardTitle>
                <CardDescription>Specialists share this one bounded foreground session.</CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                {sourceOnly ? <Badge variant="outline">Source-only</Badge> : null}
                <Badge variant="secondary">{config.authority} authority</Badge>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm font-medium" htmlFor="tutor-role">
                Tutor role
                <select
                  id="tutor-role"
                  aria-label="Tutor role"
                  value={role}
                  onChange={(event) => changeRole(event.target.value as StudyAssistantRole)}
                  className="border-input bg-background mt-1 flex h-9 w-full rounded-md border px-3 text-sm"
                  disabled={invocation.isPending}
                >
                  {STUDY_ASSISTANT_ROLES.map((candidate) => <option key={candidate} value={candidate}>{ROLE_LABELS[candidate]}</option>)}
                </select>
              </label>
              <label className="space-y-1 text-sm font-medium" htmlFor="tutor-mode">
                Tutor mode
                <select
                  id="tutor-mode"
                  aria-label="Tutor mode"
                  value={mode}
                  onChange={(event) => changeMode(event.target.value as TutorMode)}
                  className="border-input bg-background mt-1 flex h-9 w-full rounded-md border px-3 text-sm"
                  disabled={invocation.isPending}
                >
                  {TUTOR_MODES.map((candidate) => <option key={candidate} value={candidate}>{modeLabel(candidate)}</option>)}
                </select>
              </label>
            </div>
            {requiresWebPermission ? (
              <div className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
                <p className="font-medium">Web research is off until you request it.</p>
                {!webPermissionRequested ? (
                  <Button type="button" variant="outline" onClick={() => setWebPermissionRequested(true)} disabled={invocation.isPending}>
                    Request web research permission
                  </Button>
                ) : (
                  <p role="status" className="text-muted-foreground">Web research permission requested for this invocation.</p>
                )}
                {!hasApprovedScope ? <p className="text-xs text-muted-foreground">The plan must provide an approved HTTPS scope before a web request can be sent.</p> : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4 p-4">
            <label className="block space-y-1 text-sm font-medium" htmlFor="tutor-prompt">
              What would you like to learn?
              <Textarea
                id="tutor-prompt"
                aria-label="Tutor prompt"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={`Try “${modeLabel(mode)}…”`}
                rows={4}
                disabled={invocation.isPending}
              />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" onClick={() => void submit()} disabled={invocation.isPending || !prompt.trim()}>
                {invocation.isPending ? 'Tutor is working…' : 'Ask tutor'}
              </Button>
              <Button type="button" variant="outline" onClick={invocation.cancel} disabled={!invocation.isPending}>
                Cancel tutor invocation
              </Button>
              {invocation.isError ? <Button type="button" variant="outline" onClick={() => void invocation.retry()}>Retry</Button> : null}
            </div>
            {invocation.isPending ? <p role="status" className="text-sm text-muted-foreground">Tutor is working on this one foreground request…</p> : null}
            {invocation.isCancelled ? <p role="status" className="text-sm text-muted-foreground">Tutor invocation cancelled. Nothing was changed.</p> : null}
            {invocation.isError ? <p role="alert" className="text-sm text-destructive">{safeErrorMessage(invocation.error)}</p> : null}
            {actionStatus ? <p role="status" className="text-sm text-muted-foreground">{actionStatus}</p> : null}

            {(localResponse ?? invocation.data) ? (
              <div className="space-y-4 border-t pt-4">
                <div className="whitespace-pre-wrap text-sm leading-6">{(localResponse ?? invocation.data)?.answer}</div>
                {(localResponse ?? invocation.data)?.citations.length ? (
                  <div className="space-y-2" aria-label="Tutor citations">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Evidence</p>
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
                  <div className="space-y-2" aria-label="Tutor proposals">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Proposed actions</p>
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
          Tutor dock is compact. Reopen it to continue the foreground conversation.
        </div>
      )}

      <Dialog open={proposal !== null} onOpenChange={(open) => { if (!open) { setProposal(null); setProposalError(null) } }}>
        <DialogContent aria-label="Review tutor proposal">
          <DialogHeader>
            <DialogTitle>Review tutor proposal</DialogTitle>
            <DialogDescription>
              The tutor only suggested this action. Review it before any existing navigation or plan mutation is invoked.
            </DialogDescription>
          </DialogHeader>
          {proposal ? (
            <div className="space-y-2 rounded-md border bg-muted/20 p-3 text-sm">
              <p className="font-medium">{proposal.label}</p>
              <p className="text-muted-foreground">Action: <code>{proposal.action}</code></p>
              {proposal.action !== 'plan.propose.syllabus' && !navigationTarget(proposal, planId, selectedSources[0]) ? (
                <p className="text-amber-700">Unavailable until a later Study Workbench stage. Nothing will be changed.</p>
              ) : null}
            </div>
          ) : null}
          {proposalError ? <p role="alert" className="text-sm text-destructive">{proposalError}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => { setProposal(null); setProposalError(null) }} disabled={proposeSyllabus.isPending}>Cancel</Button>
            <Button type="button" onClick={() => void applyProposal()} disabled={proposeSyllabus.isPending}>
              {proposal && navigationTarget(proposal, planId, selectedSources[0]) ? 'Open destination' : 'Confirm proposal'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
