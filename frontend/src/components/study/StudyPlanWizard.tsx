'use client'

import { useEffect, useRef, useState } from 'react'

import { StudySourcePicker } from '@/components/study/StudySourcePicker'
import type { StudySourcePickerProps } from '@/components/study/StudySourcePicker'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  useAddStudyPlanSource,
  useCreateStudyPlan,
  useStudyPlan,
} from '@/lib/hooks/use-study-plans'

interface StudyPlanWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Returns an i18n key; the caller translates it where it renders. */
function safeErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return 'study.studyPlanWizard.errors.conflict'
  if (status === 503) return 'study.studyPlanWizard.errors.unavailable'
  return 'study.studyPlanWizard.errors.saveFailed'
}

export function StudyPlanWizard({ open, onOpenChange }: StudyPlanWizardProps) {
  const { t } = useTranslation()
  const [goal, setGoal] = useState('')
  const [startingLevel, setStartingLevel] = useState('beginner')
  const [targetDate, setTargetDate] = useState('')
  const [step, setStep] = useState<1 | 2>(1)
  const [draftPlanId, setDraftPlanId] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const draftRevisionRef = useRef<number | null>(null)
  const createPlan = useCreateStudyPlan()
  const linkSource = useAddStudyPlanSource()
  const draftPlan = useStudyPlan(draftPlanId)
  const { openSourceDialog } = useCreateDialogs()

  useEffect(() => {
    if (!open) return
    setStep(draftPlanId ? 2 : 1)
  }, [open, draftPlanId])

  useEffect(() => {
    const serverRevision = draftPlan.data?.version
    if (typeof serverRevision !== 'number') return
    draftRevisionRef.current = draftRevisionRef.current === null
      ? serverRevision
      : Math.max(draftRevisionRef.current, serverRevision)
  }, [draftPlan.data?.version])

  const saveDraft = async () => {
    const normalizedGoal = goal.trim()
    const normalizedLevel = startingLevel.trim()
    if (!normalizedGoal || !normalizedLevel) {
      setSaveError('study.studyPlanWizard.errors.missingFields')
      return
    }
    setSaveError(null)
    try {
      const plan = await createPlan.mutateAsync({
        goal: normalizedGoal,
        starting_level: normalizedLevel,
        target_date: targetDate || null,
      })
      setDraftPlanId(plan.plan_id)
      draftRevisionRef.current = typeof plan.version === 'number' ? plan.version : null
      // Once the server owns the draft, do not retain its raw fields in the
      // wizard.  Reopening reads the authoritative projection by ID.
      setGoal('')
      setStartingLevel('beginner')
      setTargetDate('')
      setStep(2)
    } catch (error) {
      setSaveError(safeErrorMessage(error))
    }
  }

  const handleLinkSource = async (sourceId: string) => {
    if (!draftPlanId) throw new Error('Study plan draft is not ready')
    const revision = draftRevisionRef.current ?? draftPlan.data?.version
    if (!revision) throw new Error('Study plan draft is still loading')
    await linkSource.mutateAsync({
      planId: draftPlanId,
      input: { source_id: sourceId, expected_revision: revision },
    })
    draftRevisionRef.current = revision + 1
  }

  const handleOpenUpload: StudySourcePickerProps['onOpenUpload'] = (
    _onSourceCreated,
    onSourcesCreated,
  ) => {
    // AddSourceDialog owns ingestion. Its bounded batch callback is the
    // authoritative handoff used by StudySourcePicker to persist each link;
    // the legacy zero-argument callback remains available to other callers.
    openSourceDialog(onSourcesCreated ? { onSourcesCreated } : {})
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{step === 1 ? t('study.studyPlanWizard.createTitle') : t('study.studyPlanWizard.sourcesTitle')}</DialogTitle>
          <DialogDescription>
            {step === 1
              ? t('study.studyPlanWizard.createDescription')
              : t('study.studyPlanWizard.sourcesDescription')}
          </DialogDescription>
        </DialogHeader>

        {step === 1 ? (
          <div className="space-y-5 py-2">
            <div className="space-y-2">
              <Label htmlFor="study-plan-goal">{t('study.studyPlanWizard.goalLabel')}</Label>
              <Textarea
                id="study-plan-goal"
                aria-label={t('study.studyPlanWizard.goalLabel')}
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder={t('study.studyPlanWizard.goalPlaceholder')}
                maxLength={2_000}
                rows={4}
                autoFocus
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="study-plan-level">{t('study.studyPlanWizard.levelLabel')}</Label>
                <Input
                  id="study-plan-level"
                  value={startingLevel}
                  onChange={(event) => setStartingLevel(event.target.value)}
                  maxLength={200}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="study-plan-target-date">{t('study.studyPlanWizard.targetDateLabel')}</Label>
                <Input
                  id="study-plan-target-date"
                  type="date"
                  value={targetDate}
                  onChange={(event) => setTargetDate(event.target.value)}
                />
              </div>
            </div>
            {saveError ? <p role="alert" className="text-sm text-destructive">{t(saveError)}</p> : null}
          </div>
        ) : (
          <div className="py-2">
            {draftPlan.isLoading ? (
              <p role="status" className="rounded-md border p-4 text-sm text-muted-foreground">{t('study.studyPlanWizard.loadingDraft')}</p>
            ) : draftPlan.isError || !draftPlan.data ? (
              <p role="alert" className="rounded-md border border-destructive/40 p-4 text-sm text-destructive">
                {t('study.studyPlanWizard.draftLoadError')}
              </p>
            ) : (
              <StudySourcePicker
                links={draftPlan.data.source_links}
                onOpenUpload={handleOpenUpload}
                onLinkSource={handleLinkSource}
              />
            )}
          </div>
        )}

        <DialogFooter>
          {step === 2 ? (
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('study.studyPlanWizard.saveLater')}
            </Button>
          ) : null}
          {step === 1 ? (
            <Button type="button" onClick={() => void saveDraft()} disabled={createPlan.isPending}>
              {createPlan.isPending ? t('study.studyPlanWizard.savingDraft') : t('study.studyPlanWizard.saveAndContinue')}
            </Button>
          ) : (
            <Button type="button" onClick={() => onOpenChange(false)}>{t('study.studyPlanWizard.done')}</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
