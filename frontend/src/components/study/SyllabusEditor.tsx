'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  useApproveStudySyllabus,
  useSaveStudySyllabus,
} from '@/lib/hooks/use-study-plans'
import { STUDY_PLAN_STATE_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'
import type {
  StudyPlan,
  StudySourceReadiness,
  StudySyllabus,
  StudySyllabusUnit,
} from '@/lib/types/study-plans'

export interface SyllabusEditorProps {
  plan: StudyPlan
  syllabus: StudySyllabus
  readiness?: StudySourceReadiness | null
  readinessLoading?: boolean
  readinessError?: boolean
  onRefresh?: () => void | Promise<unknown>
}

function cloneUnits(units: readonly StudySyllabusUnit[]): StudySyllabusUnit[] {
  return units.map((unit) => ({
    ...unit,
    objectives: [...unit.objectives],
    prerequisite_unit_ids: [...unit.prerequisite_unit_ids],
    source_ids: [...unit.source_ids],
    activities: unit.activities.map((activity) => ({
      ...activity,
      source_ids: [...activity.source_ids],
    })),
  }))
}

function safeErrorMessage(error: unknown, t: (key: string) => string): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return t('study.syllabusEditor.errors.changedElsewhere')
  if (status === 503) return t('study.syllabusEditor.errors.approvalUnavailable')
  return t('study.syllabusEditor.errors.couldNotSave')
}

export function SyllabusEditor({
  plan,
  syllabus,
  readiness,
  readinessLoading = false,
  readinessError = false,
  onRefresh,
}: SyllabusEditorProps) {
  const { t } = useTranslation()
  const [units, setUnits] = useState<StudySyllabusUnit[]>(() => cloneUnits(syllabus.units))
  const [displayedVersion, setDisplayedVersion] = useState(syllabus.version)
  const [displayedManifest, setDisplayedManifest] = useState(syllabus.source_manifest_sha256)
  const [displayedPlanState, setDisplayedPlanState] = useState(plan.state)
  const [dirty, setDirty] = useState(false)
  const [approvalOpen, setApprovalOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const nextVersionRef = useRef(syllabus.version)
  const revisionRef = useRef(plan.version)
  const saveSyllabus = useSaveStudySyllabus()
  const approveSyllabus = useApproveStudySyllabus()

  useEffect(() => {
    setUnits(cloneUnits(syllabus.units))
    setDisplayedVersion(syllabus.version)
    setDisplayedManifest(syllabus.source_manifest_sha256)
    setDirty(false)
    nextVersionRef.current = syllabus.version
  }, [syllabus.plan_id, syllabus.version, syllabus.source_manifest_sha256, syllabus.units])

  useEffect(() => {
    revisionRef.current = Math.max(revisionRef.current, plan.version)
    setDisplayedPlanState(plan.state)
  }, [plan.state, plan.version])

  const sourceIds = useMemo(() => plan.source_links.map((link) => link.source_id), [plan.source_links])
  const coveredSourceIds = useMemo(() => {
    const ids = new Set(units.flatMap((unit) => [
      ...unit.source_ids,
      ...unit.activities.flatMap((activity) => activity.source_ids),
    ]))
    return new Set(sourceIds.filter((sourceId) => ids.has(sourceId)))
  }, [sourceIds, units])
  const readinessById = useMemo(
    () => new Map((readiness?.items ?? []).map((item) => [item.source_id, item])),
    [readiness?.items],
  )
  const readinessGaps = useMemo(() => sourceIds.flatMap((sourceId) => {
    const item = readinessById.get(sourceId)
    if (!item) return [{ sourceId, label: t('study.syllabusEditor.readinessUnavailable') }]
    if (!item.ready || item.reason !== 'ready') {
      return [{ sourceId, label: t('study.syllabusEditor.sourceNotReady', { title: item.title }) }]
    }
    if (item.fingerprint_status !== 'available') {
      return [{ sourceId, label: t('study.syllabusEditor.sourceFingerprintDrift', { title: item.title }) }]
    }
    return []
  }), [readinessById, sourceIds, t])
  const uncoveredGaps = sourceIds.filter((sourceId) => !coveredSourceIds.has(sourceId))
  const approvalBlocked = Boolean(
    dirty ||
    displayedPlanState !== 'editing' ||
    readinessLoading ||
    readinessError ||
    !readiness ||
    !readiness.ready ||
    readinessGaps.length > 0 ||
    uncoveredGaps.length > 0,
  )

  const updateUnit = (index: number, update: Partial<StudySyllabusUnit>) => {
    setUnits((current) => current.map((unit, unitIndex) => (
      unitIndex === index ? { ...unit, ...update } : unit
    )))
    setDirty(true)
    setSavedMessage(null)
  }

  const updateObjective = (unitIndex: number, objectiveIndex: number, value: string) => {
    const nextObjectives = units[unitIndex].objectives.map((objective, index) => (
      index === objectiveIndex ? value : objective
    ))
    updateUnit(unitIndex, { objectives: nextObjectives })
  }

  const persistUnits = async (nextUnits: StudySyllabusUnit[]) => {
    setError(null)
    setSavedMessage(null)
    const version = Math.max(nextVersionRef.current, displayedVersion) + 1
    const expectedRevision = revisionRef.current
    try {
      const saved = await saveSyllabus.mutateAsync({
        planId: plan.plan_id,
        input: {
          expected_revision: expectedRevision,
          version,
          source_manifest_sha256: displayedManifest,
          units: nextUnits,
        },
      })
      const savedVersion = Math.max(version, saved?.version ?? 0)
      nextVersionRef.current = savedVersion
      revisionRef.current = expectedRevision + 1
      setDisplayedVersion(savedVersion)
      setDisplayedManifest(saved?.source_manifest_sha256 ?? displayedManifest)
      setDisplayedPlanState('editing')
      setUnits(cloneUnits(saved?.units ?? nextUnits))
      setDirty(false)
      setSavedMessage(t('study.syllabusEditor.savedVersion', { version: savedVersion }))
    } catch (mutationError) {
      setError(safeErrorMessage(mutationError, t))
    }
  }

  const moveUnit = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= units.length || saveSyllabus.isPending) return
    const nextUnits = [...units]
    const [moved] = nextUnits.splice(index, 1)
    nextUnits.splice(target, 0, moved)
    setUnits(nextUnits)
    void persistUnits(nextUnits)
  }

  const approve = async () => {
    setError(null)
    try {
      await approveSyllabus.mutateAsync({
        planId: plan.plan_id,
        input: { syllabus_version: displayedVersion, expected_revision: revisionRef.current },
      })
      setApprovalOpen(false)
      setDisplayedPlanState('approved')
      setSavedMessage(t('study.syllabusEditor.approvedVersion', { version: displayedVersion }))
    } catch (mutationError) {
      setError(safeErrorMessage(mutationError, t))
    }
  }

  const blockReason = readinessLoading
    ? t('study.syllabusEditor.block.loading')
    : readinessError || !readiness
      ? t('study.syllabusEditor.block.refreshNeeded')
      : readinessGaps.length > 0
        ? t('study.syllabusEditor.block.sourceNotReady')
        : uncoveredGaps.length > 0
          ? t('study.syllabusEditor.block.uncovered')
          : dirty
            ? t('study.syllabusEditor.block.unsaved')
            : plan.state !== 'editing'
              ? t('study.syllabusEditor.block.editFirst')
              : null

  return (
    <div className="space-y-5 motion-reduce:transition-none" aria-busy={saveSyllabus.isPending || approveSyllabus.isPending}>
      <div className="flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
        <p className="text-sm font-medium">{t('study.syllabusEditor.versionImmutable', { version: displayedVersion })}</p>
          <p className="text-sm text-muted-foreground">
            {t('study.syllabusEditor.immutableHint')}
          </p>
        </div>
        <Badge variant={displayedPlanState === 'approved' ? 'default' : 'outline'}>{enumLabel(t, STUDY_PLAN_STATE_KEYS, displayedPlanState, spacedEnum(displayedPlanState))}</Badge>
      </div>

      <section aria-labelledby="syllabus-coverage-heading" className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="syllabus-coverage-heading" className="text-lg font-semibold">{t('study.syllabusEditor.sourceCoverage')}</h2>
          <p className="text-sm font-medium">{t('study.syllabusEditor.coverageCount', { covered: coveredSourceIds.size, total: sourceIds.length })}</p>
        </div>
        {uncoveredGaps.length > 0 || readinessGaps.length > 0 ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
            <p className="text-sm font-medium">{t('study.syllabusEditor.coverageGaps')}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {uncoveredGaps.map((sourceId) => <li key={`uncovered-${sourceId}`}>{t('study.syllabusEditor.sourceNotCovered', { sourceId })}</li>)}
              {readinessGaps.map((gap) => <li key={`readiness-${gap.sourceId}`}>{gap.label}</li>)}
            </ul>
          </div>
        ) : (
          // v0.8.130 — status colours from theme tokens (UI audit Phase 1)
          <p className="rounded-md border border-success/30 bg-success-soft p-3 text-sm">{t('study.syllabusEditor.allCovered')}</p>
        )}
      </section>

      {error ? (
        <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3" role="alert">
          <p className="text-sm text-destructive">{error}</p>
          {onRefresh ? <Button type="button" variant="outline" onClick={() => void onRefresh()}>{t('study.syllabusEditor.refreshSyllabus')}</Button> : null}
        </div>
      ) : null}
      {savedMessage ? <p role="status" className="text-sm text-muted-foreground">{savedMessage}</p> : null}
      {blockReason ? <p className="rounded-md border border-warning/40 bg-warning-soft p-3 text-sm">{blockReason}</p> : null}

      <div className="space-y-3" aria-label={t('study.syllabusEditor.unitsLabel')}>
        {units.map((unit, index) => (
          <Card key={unit.unit_id}>
            <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 flex-1 space-y-2">
                <CardDescription>{t('study.syllabusEditor.unitMeta', { index: index + 1, minutes: unit.estimated_minutes })}</CardDescription>
                <Input
                  aria-label={t('study.syllabusEditor.titleAria', { title: unit.title })}
                  value={unit.title}
                  maxLength={200}
                  onChange={(event) => updateUnit(index, { title: event.target.value })}
                />
              </div>
              <div className="flex shrink-0 gap-2" aria-label={t('study.syllabusEditor.reorderAria', { title: unit.title })}>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label={t('study.syllabusEditor.moveUpAria', { title: unit.title })}
                  disabled={index === 0 || saveSyllabus.isPending}
                  onClick={() => moveUnit(index, -1)}
                >
                  {t('study.syllabusEditor.moveUp')}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label={t('study.syllabusEditor.moveDownAria', { title: unit.title })}
                  disabled={index === units.length - 1 || saveSyllabus.isPending}
                  onClick={() => moveUnit(index, 1)}
                >
                  {t('study.syllabusEditor.moveDown')}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-2">
                <p className="text-sm font-medium">{t('study.syllabusEditor.objectives')}</p>
                {unit.objectives.map((objective, objectiveIndex) => (
                  <Textarea
                    key={`${unit.unit_id}-objective-${objectiveIndex}`}
                    aria-label={t('study.syllabusEditor.objectiveAria', { title: unit.title, number: objectiveIndex + 1 })}
                    value={objective}
                    maxLength={2_000}
                    rows={2}
                    onChange={(event) => updateObjective(index, objectiveIndex, event.target.value)}
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                {unit.source_ids.map((sourceId) => <Badge key={sourceId} variant="secondary">{sourceId}</Badge>)}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={!dirty || saveSyllabus.isPending}
          onClick={() => void persistUnits(units)}
        >
          {saveSyllabus.isPending ? t('study.syllabusEditor.savingVersion') : t('study.syllabusEditor.saveNewVersion')}
        </Button>
        <AlertDialog open={approvalOpen} onOpenChange={setApprovalOpen}>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              disabled={approvalBlocked || approveSyllabus.isPending}
              aria-label={t('study.syllabusEditor.approveVersion', { version: displayedVersion })}
            >
              {approveSyllabus.isPending ? t('study.syllabusEditor.approving') : t('study.syllabusEditor.approveVersion', { version: displayedVersion })}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('study.syllabusEditor.approveDialogTitle', { version: displayedVersion })}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('study.syllabusEditor.approveDialogDescription', { version: displayedVersion, covered: coveredSourceIds.size, total: sourceIds.length })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={approveSyllabus.isPending}>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={() => void approve()}>{t('study.syllabusEditor.confirmApproval')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  )
}
