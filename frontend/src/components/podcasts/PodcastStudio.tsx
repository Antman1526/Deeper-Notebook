'use client'

import { markErrorReported } from '@/lib/api/client'
import { useMemo, useRef, useState } from 'react'

import type { TFunction } from 'i18next'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { podcastsApi } from '@/lib/api/podcasts'
import type { PodcastProductionRole, PodcastReadiness } from '@/lib/types/podcasts'
import type { PodcastSelection } from '@/lib/podcasts/selection'
import { EditorialBriefPanel, type EditorialBriefValues } from './EditorialBriefPanel'
import { OutlineStoryboard } from './OutlineStoryboard'
import { PodcastModelPlan, type PodcastModelPlanItem } from './PodcastModelPlan'
import { ProductionTimeline, type PodcastStudioState } from './ProductionTimeline'
import { ResearchSetPanel } from './ResearchSetPanel'
import { PodcastStudioFolio } from '@/components/deeper-notebook/studios/PodcastStudioFolio'

export interface PodcastStudioProps {
  seedDocumentIds: string[]
  selections?: PodcastSelection[]
  // v0.8.127 — the notebook this Studio session was opened from, if any
  // (see usePodcastStudioStore's `notebookId`). Passed straight through to
  // the submit so the resulting episode is notebook-scoped. Undefined/null
  // when the Studio was opened globally.
  notebookId?: string | null
  headingLevel?: 1 | 2
  modelPlans?: Array<{
    label: string
    stage?: PodcastModelPlanItem['stage']
    overrideChoices?: string[]
    plan?: Partial<PodcastModelPlanItem> & { outcome: PodcastModelPlanItem['outcome']; reason: string }
  }>
  initialState?: PodcastStudioState
  onStateChange?: (state: PodcastStudioState) => void
}

const defaultBrief: EditorialBriefValues = {
  centralQuestion: '',
  audience: 'practitioner',
  purpose: 'explain',
  format: 'deep_dive',
  targetMinutes: 20,
  requiredTakeaway: '',
  includeUnansweredQuestions: false,
  evidencePolicy: 'strict',
  episodeProfileName: '',
  speakerProfileName: '',
}

const outlineDefaults = ['Introduction', 'Findings', 'Takeaway']
const stageDefaults: Array<{ stage: PodcastModelPlanItem['stage']; labelKey: string; role: PodcastModelPlanItem['role'] }> = [
  { stage: 'outline', labelKey: 'podcasts.podcastStudio.outlineRoute', role: 'podcast_outline' },
  { stage: 'script', labelKey: 'podcasts.podcastStudio.scriptRoute', role: 'podcast_script' },
  { stage: 'voice', labelKey: 'podcasts.podcastStudio.voiceRoute', role: 'text_to_speech' },
  { stage: 'transcription', labelKey: 'podcasts.podcastStudio.transcriptionRoute', role: 'speech_to_text' },
]
const knowledgeRouteDefaults: Array<{ stage: PodcastModelPlanItem['stage']; role: PodcastModelPlanItem['role'] }> = [
  { stage: 'evidence', role: 'evidence_extraction' },
  { stage: 'outline', role: 'podcast_outline' },
  { stage: 'script', role: 'podcast_script' },
  { stage: 'verification', role: 'claim_verification' },
  { stage: 'voice', role: 'text_to_speech' },
]

function selectionsFromSeeds(seedDocumentIds: string[]): PodcastSelection[] {
  return seedDocumentIds.map((documentId) => ({ kind: 'knowledge_document', documentId }))
}

function normalizeProductionOverrides(overrides: Partial<Record<PodcastProductionRole, string>>): Partial<Record<PodcastProductionRole, string>> {
  const normalized: Partial<Record<PodcastProductionRole, string>> = {}
  for (const role of Object.keys(overrides).sort() as PodcastProductionRole[]) {
    const modelId = overrides[role]
    if (modelId) normalized[role] = modelId
  }
  return normalized
}

function sameProductionOverrides(
  left: Partial<Record<PodcastProductionRole, string>>,
  right: Partial<Record<PodcastProductionRole, string>>,
): boolean {
  const normalizedLeft = normalizeProductionOverrides(left)
  const normalizedRight = normalizeProductionOverrides(right)
  const leftRoles = Object.keys(normalizedLeft) as PodcastProductionRole[]
  const rightRoles = Object.keys(normalizedRight) as PodcastProductionRole[]
  return leftRoles.length === rightRoles.length && leftRoles.every((role) => normalizedLeft[role] === normalizedRight[role])
}

function toProvidedPlanItems(modelPlans: PodcastStudioProps['modelPlans'], t: TFunction): PodcastModelPlanItem[] {
  return modelPlans?.map((item, index) => {
    const defaults = knowledgeRouteDefaults[index] ?? stageDefaults[index] ?? stageDefaults[0]
    return {
      stage: item.stage ?? defaults.stage,
      label: item.label,
      role: item.plan?.role ?? defaults.role,
      outcome: item.plan?.outcome ?? 'blocked',
      reason: item.plan?.reason ?? t('podcasts.podcastStudio.routePlanUnavailable'),
      modelId: item.plan?.modelId ?? null,
      provider: item.plan?.provider ?? null,
      resourceTier: item.plan?.resourceTier ?? null,
      selectionSource: item.plan?.selectionSource ?? null,
      overrideChoices: item.overrideChoices ?? [],
    }
  }) ?? []
}

function toReadinessPlanItem(plan: PodcastReadiness['stagePlans'][number], t: TFunction): PodcastModelPlanItem {
  const defaults = stageDefaults.find((item) => item.role === plan.role) ?? stageDefaults[0]
  return {
    stage: defaults.stage,
    label: t(defaults.labelKey),
    role: plan.role,
    outcome: plan.outcome,
    reason: plan.reason,
    modelId: plan.modelId,
    provider: plan.provider,
    resourceTier: plan.resourceTier,
    selectionSource: plan.selectionSource,
    overrideChoices: plan.overrideChoices ?? [],
  }
}

function toPlanItems(modelPlans: PodcastStudioProps['modelPlans'], readiness: PodcastReadiness | null, t: TFunction): PodcastModelPlanItem[] {
  const provided = toProvidedPlanItems(modelPlans, t)
  if (!readiness) return provided

  const freshByRole = new Map(readiness.stagePlans.map((plan) => [plan.role, toReadinessPlanItem(plan, t)]))
  const merged = provided.flatMap((plan) => {
    const productionRole = productionRoleForPlan(plan)
    if (!productionRole) return [plan]
    const fresh = freshByRole.get(productionRole)
    if (!fresh) return []
    freshByRole.delete(productionRole)
    return [{ ...fresh, label: plan.label }]
  })
  const remainingFresh = readiness.stagePlans
    .map((plan) => freshByRole.get(plan.role))
    .filter((plan): plan is PodcastModelPlanItem => Boolean(plan))
  return [...merged, ...remainingFresh]
}

function productionRoleForPlan(plan: PodcastModelPlanItem): PodcastProductionRole | null {
  return plan.role === 'podcast_outline' || plan.role === 'podcast_script' || plan.role === 'text_to_speech' || plan.role === 'speech_to_text'
    ? plan.role
    : null
}

/**
 * Shared Phase-2 Studio controller. The route and Knowledge pane render this
 * exact controller; presentation components remain controlled and have no
 * network effects on mount.
 */
export function PodcastStudio({ seedDocumentIds, selections, notebookId, headingLevel = 2, modelPlans = [], initialState = 'selecting', onStateChange }: PodcastStudioProps) {
  const { t } = useTranslation()
  const resolvedSelections = useMemo(() => selections ?? selectionsFromSeeds(seedDocumentIds), [seedDocumentIds, selections])
  const [brief, setBrief] = useState<EditorialBriefValues>(defaultBrief)
  const [outline, setOutline] = useState<string[]>(outlineDefaults)
  const [readiness, setReadiness] = useState<PodcastReadiness | null>(null)
  const [episodeProfiles, setEpisodeProfiles] = useState<string[]>([])
  const [speakerProfiles, setSpeakerProfiles] = useState<string[]>([])
  const [modelOverrides, setModelOverrides] = useState<Partial<Record<PodcastProductionRole, string>>>({})
  const [studioState, setStudioStateInternal] = useState<PodcastStudioState>(initialState)
  const [productionPhase, setProductionPhase] = useState<'review' | 'confirm'>('review')
  const [isPreparing, setIsPreparing] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  // Holds an i18n key, translated where it renders.
  const [productionError, setProductionError] = useState<string | null>(null)
  const [submittedMessage, setSubmittedMessage] = useState<string | null>(null)
  const submissionKey = useRef<string | null>(null)
  const readinessGeneration = useRef(0)
  const modelOverridesRef = useRef(modelOverrides)

  const setStudioState = (next: PodcastStudioState) => {
    setStudioStateInternal(next)
    onStateChange?.(next)
  }

  const prepareProductionReview = async () => {
    if (isPreparing || resolvedSelections.length === 0) return
    const requestGeneration = readinessGeneration.current + 1
    const requestOverrides = normalizeProductionOverrides(modelOverridesRef.current)
    const isCurrentRequest = () => (
      readinessGeneration.current === requestGeneration
      && sameProductionOverrides(modelOverridesRef.current, requestOverrides)
    )
    readinessGeneration.current = requestGeneration
    setIsPreparing(true)
    setProductionError(null)
    setSubmittedMessage(null)
    try {
      const [nextReadiness, nextEpisodeProfiles, nextSpeakerProfiles] = await Promise.all([
        Object.keys(requestOverrides).length > 0
          ? podcastsApi.getPodcastReadiness(resolvedSelections, { productionOverrides: requestOverrides })
          : podcastsApi.getPodcastReadiness(resolvedSelections),
        podcastsApi.listEpisodeProfiles(),
        podcastsApi.listSpeakerProfiles(),
      ])
      if (!isCurrentRequest()) return
      setReadiness(nextReadiness)
      const nextEpisodeNames = nextEpisodeProfiles.map((profile) => profile.name)
      const nextSpeakerNames = nextSpeakerProfiles.map((profile) => profile.name)
      setEpisodeProfiles(nextEpisodeNames)
      setSpeakerProfiles(nextSpeakerNames)
      setBrief((current) => ({
        ...current,
        episodeProfileName: current.episodeProfileName || nextEpisodeNames[0] || '',
        speakerProfileName: current.speakerProfileName || nextSpeakerNames[0] || '',
      }))
      setStudioState(nextReadiness.ready ? 'briefing_ready' : 'preview_ready')
      setProductionPhase('review')
    } catch (error) {
      markErrorReported(error) // v0.8.130 — this caller reports the failure itself
      if (isCurrentRequest()) setProductionError('podcasts.podcastStudio.readinessUnavailable')
    } finally {
      if (isCurrentRequest()) setIsPreparing(false)
    }
  }

  const canConfirm = Boolean(
    readiness?.ready
      && readiness.preview.selectionFingerprint
      && brief.episodeProfileName
      && brief.speakerProfileName,
  )

  const confirmProduction = async () => {
    if (!readiness || !canConfirm || isSubmitting) return
    setIsSubmitting(true)
    setProductionError(null)
    submissionKey.current ??= `podcast-studio-${crypto.randomUUID()}`
    try {
      const submitted = await podcastsApi.submitStudioPodcast({
        selections: resolvedSelections,
        selectionFingerprint: readiness.preview.selectionFingerprint,
        idempotencyKey: submissionKey.current,
        episodeProfile: brief.episodeProfileName,
        speakerProfile: brief.speakerProfileName,
        episodeName: readiness.preview.entries[0]?.title ?? 'Deeper Notebook podcast',
        notebookId: notebookId ?? undefined,
        mode: brief.format,
        reviewOutline: true,
        productionOverrides: modelOverrides,
        editorialBrief: {
          centralQuestion: brief.centralQuestion || null,
          audience: brief.audience,
          purpose: brief.purpose,
          format: brief.format,
          targetMinutes: brief.targetMinutes,
          requiredTakeaway: brief.requiredTakeaway || null,
          includeUnansweredQuestions: brief.includeUnansweredQuestions,
          evidencePolicy: brief.evidencePolicy,
          episodeProfileName: brief.episodeProfileName,
          speakerProfileName: brief.speakerProfileName,
          outline,
        },
      })
      setStudioState('submitted')
      setStudioState('awaiting_outline')
      setSubmittedMessage(t('podcasts.podcastStudio.productionSubmitted', { name: submitted.episodeName }))
    } catch (error) {
      markErrorReported(error) // v0.8.130 — this caller reports the failure itself
      setProductionError('podcasts.podcastStudio.submitFailed')
      setStudioState('briefing_ready')
    } finally {
      setIsSubmitting(false)
    }
  }

  const plans = toPlanItems(modelPlans, readiness, t)
  const planChoices = Object.fromEntries(
    plans.filter((plan) => (plan.overrideChoices?.length ?? 0) > 0).map((plan) => [plan.stage, plan.overrideChoices ?? []]),
  ) as Partial<Record<PodcastModelPlanItem['stage'], string[]>>
  const displayedPlans = plans.map((plan) => {
    const productionRole = productionRoleForPlan(plan)
    const pendingOverride = productionRole ? modelOverrides[productionRole] : undefined
    if (readiness || !pendingOverride) return plan
    return { ...plan, modelId: pendingOverride, pendingOverride: true }
  })

  const handleOverride = (stage: PodcastModelPlanItem['stage'], modelId: string) => {
    const selectedPlan = plans.find((plan) => plan.stage === stage)
    const role = selectedPlan ? productionRoleForPlan(selectedPlan) : null
    if (!role) return
    const nextOverrides = { ...modelOverridesRef.current }
    if (modelId) nextOverrides[role] = modelId
    else delete nextOverrides[role]
    modelOverridesRef.current = normalizeProductionOverrides(nextOverrides)
    readinessGeneration.current += 1
    setModelOverrides(modelOverridesRef.current)
    setReadiness(null)
    setProductionPhase('review')
    setProductionError(null)
    setIsPreparing(false)
    setStudioState('selecting')
  }

  const Heading = headingLevel === 1 ? 'h1' : 'h2'

  return (
    <section aria-label={t('podcasts.podcastStudio.title')} className="space-y-5">
      <header>
        <Heading className="text-xl font-semibold">{t('podcasts.podcastStudio.title')}</Heading>
        <p className="mt-1 text-sm text-muted-foreground">{t('podcasts.podcastStudio.description')}</p>
      </header>

      <PodcastStudioFolio
        researchSet={<ResearchSetPanel selections={resolvedSelections} preview={readiness?.preview ?? null} />}
        editorialBrief={<EditorialBriefPanel value={brief} onChange={(patch) => setBrief((current) => ({ ...current, ...patch }))} episodeProfiles={episodeProfiles} speakerProfiles={speakerProfiles} />}
        storyboard={<section data-studio-region="outline-workspace" data-region="outline-workspace" aria-label={t('podcasts.podcastStudio.outlineWorkspace')} className="space-y-4">
          <OutlineStoryboard
            segments={outline}
            onChange={(next) => setOutline(next.map((segment) => typeof segment === 'string' ? segment : segment.title ?? segment.name ?? segment.id ?? 'Untitled segment'))}
          />
        </section>}
        modelPlan={<PodcastModelPlan
            plans={displayedPlans}
            overrideChoices={planChoices}
            onOverride={handleOverride}
          />}
        production={<ProductionTimeline state={studioState}>
          <section aria-label={t('podcasts.podcastStudio.productionReview')} className="space-y-3 rounded-md border p-3">
            <h4 className="font-medium">{t('podcasts.podcastStudio.productionReview')}</h4>
            <p className="text-sm text-muted-foreground">{t('podcasts.podcastStudio.reviewDescription')}</p>
            {!readiness ? (
              <div className="flex flex-wrap items-center gap-2">
                <Button className="max-w-full whitespace-normal text-left" type="button" onClick={() => void prepareProductionReview()} disabled={isPreparing || resolvedSelections.length === 0}>
                  {isPreparing ? t('podcasts.podcastStudio.checkingReadiness') : t('podcasts.podcastStudio.prepareReview')}
                </Button>
                {resolvedSelections.length === 0 ? <p className="text-sm text-muted-foreground">{t('podcasts.podcastStudio.chooseSource')}</p> : null}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">{readiness.ready ? t('podcasts.podcastStudio.readinessVerified') : readiness.blockedReasons.join(', ') || t('podcasts.podcastStudio.readinessBlocked')}</p>
                <h5 className="text-sm font-medium">{t('podcasts.podcastStudio.productionProfiles')}</h5>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-1 text-sm" htmlFor="podcast-episode-profile-review">{t('podcasts.podcastStudio.episodeProfile')}
                    <select id="podcast-episode-profile-review" aria-label={t('podcasts.podcastStudio.episodeProfileForProduction')} value={brief.episodeProfileName} onChange={(event) => setBrief((current) => ({ ...current, episodeProfileName: event.target.value }))} className="h-9 rounded-md border bg-background px-2"><option value="">{t('podcasts.podcastStudio.chooseProfile')}</option>{episodeProfiles.map((name) => <option key={name} value={name}>{name}</option>)}</select>
                  </label>
                  <label className="grid gap-1 text-sm" htmlFor="podcast-speaker-profile-review">{t('podcasts.podcastStudio.voiceProfile')}
                    <select id="podcast-speaker-profile-review" aria-label={t('podcasts.podcastStudio.voiceProfileForProduction')} value={brief.speakerProfileName} onChange={(event) => setBrief((current) => ({ ...current, speakerProfileName: event.target.value }))} className="h-9 rounded-md border bg-background px-2"><option value="">{t('podcasts.podcastStudio.chooseProfile')}</option>{speakerProfiles.map((name) => <option key={name} value={name}>{name}</option>)}</select>
                  </label>
                </div>
                {productionPhase === 'review' ? (
                  <Button type="button" onClick={() => setProductionPhase('confirm')} disabled={!canConfirm}>{t('podcasts.podcastStudio.continueToConfirmation')}</Button>
                ) : (
                  <div className="space-y-2 rounded border bg-muted/20 p-3">
                    <p className="text-sm">{t('podcasts.podcastStudio.confirmDescription')}</p>
                    <Button type="button" onClick={() => void confirmProduction()} disabled={!canConfirm || isSubmitting}>{isSubmitting ? t('podcasts.podcastStudio.submitting') : t('podcasts.podcastStudio.confirmProduction')}</Button>
                  </div>
                )}
              </div>
            )}
            {productionError ? <p role="alert" className="text-sm text-destructive">{t(productionError)}</p> : null}
            {submittedMessage ? <p role="status" className="text-sm text-muted-foreground">{submittedMessage}</p> : null}
          </section>
        </ProductionTimeline>}
        review={<p className="text-sm text-muted-foreground">{t('podcasts.podcastStudio.openingNotice')}</p>}
      />
    </section>
  )
}
