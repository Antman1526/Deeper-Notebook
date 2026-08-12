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
import {
  useAddStudyPlanSource,
  useCreateStudyPlan,
  useStudyPlan,
} from '@/lib/hooks/use-study-plans'

interface StudyPlanWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function safeErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return 'This plan changed elsewhere. Close and reopen it to continue.'
  if (status === 503) return 'Study plans are temporarily unavailable. Try again shortly.'
  return 'The draft could not be saved. Nothing was lost; try again.'
}

export function StudyPlanWizard({ open, onOpenChange }: StudyPlanWizardProps) {
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
      setSaveError('Add a learning goal and starting level before continuing.')
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
          <DialogTitle>{step === 1 ? 'Create a study plan' : 'Choose learning sources'}</DialogTitle>
          <DialogDescription>
            {step === 1
              ? 'Save a small server-backed draft first. You can close this window and return to source selection later.'
              : 'Link existing sources without copying their content or local paths. The draft remains on the server while you decide.'}
          </DialogDescription>
        </DialogHeader>

        {step === 1 ? (
          <div className="space-y-5 py-2">
            <div className="space-y-2">
              <Label htmlFor="study-plan-goal">Learning goal</Label>
              <Textarea
                id="study-plan-goal"
                aria-label="Learning goal"
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder="What do you want to understand or be able to do?"
                maxLength={2_000}
                rows={4}
                autoFocus
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="study-plan-level">Starting level</Label>
                <Input
                  id="study-plan-level"
                  value={startingLevel}
                  onChange={(event) => setStartingLevel(event.target.value)}
                  maxLength={200}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="study-plan-target-date">Target date (optional)</Label>
                <Input
                  id="study-plan-target-date"
                  type="date"
                  value={targetDate}
                  onChange={(event) => setTargetDate(event.target.value)}
                />
              </div>
            </div>
            {saveError ? <p role="alert" className="text-sm text-destructive">{saveError}</p> : null}
          </div>
        ) : (
          <div className="py-2">
            {draftPlan.isLoading ? (
              <p role="status" className="rounded-md border p-4 text-sm text-muted-foreground">Loading saved draft…</p>
            ) : draftPlan.isError || !draftPlan.data ? (
              <p role="alert" className="rounded-md border border-destructive/40 p-4 text-sm text-destructive">
                The saved draft could not be loaded. Close and reopen the wizard to retry.
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
              Save and finish later
            </Button>
          ) : null}
          {step === 1 ? (
            <Button type="button" onClick={() => void saveDraft()} disabled={createPlan.isPending}>
              {createPlan.isPending ? 'Saving draft…' : 'Save and continue'}
            </Button>
          ) : (
            <Button type="button" onClick={() => onOpenChange(false)}>Done</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
