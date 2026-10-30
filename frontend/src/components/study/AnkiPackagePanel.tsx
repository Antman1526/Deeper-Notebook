'use client'

import { useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { useStudyAnkiExport, useStudyAnkiImportPreview, useStudyAnkiPublish } from '@/lib/hooks/use-study-anki'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { AnkiImportPreview } from '@/lib/types/study-anki'

const IMPORTABLE_STATES = new Set(['approved', 'generating', 'active', 'completed'])

export interface AnkiPackagePanelProps {
  planId: string
  lifecycleState?: string
  enabled?: boolean
}

function requestId(): string {
  const uuid = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `anki-import:${uuid}`.slice(0, 256)
}

/** Returns an i18n key; the caller translates it where it renders. */
function safeMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return 'study.ankiPackagePanel.errors.conflict'
  if (status === 422) return 'study.ankiPackagePanel.errors.unreadable'
  if (status === 503) return 'study.ankiPackagePanel.errors.unavailable'
  return 'study.ankiPackagePanel.errors.failed'
}

export function AnkiPackagePanel({ planId, lifecycleState = 'approved', enabled = true }: AnkiPackagePanelProps) {
  const { t } = useTranslation()
  const previewMutation = useStudyAnkiImportPreview()
  const publishMutation = useStudyAnkiPublish()
  const exportMutation = useStudyAnkiExport()
  const [preview, setPreview] = useState<AnkiImportPreview | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [errorAction, setErrorAction] = useState<'preview' | 'publish' | null>(null)
  const [published, setPublished] = useState(false)
  const publishRequestId = useRef<string | null>(null)
  const lastFile = useRef<File | null>(null)

  if (!enabled || !IMPORTABLE_STATES.has(lifecycleState)) {
    return (
      <Card role="status" aria-live="polite">
        <CardHeader><CardTitle>{t('study.ankiPackagePanel.unavailableTitle')}</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">{t('study.ankiPackagePanel.unavailableDescription')}</p></CardContent>
      </Card>
    )
  }

  const onFile = async (file: File | undefined) => {
    if (!file) return
    lastFile.current = file
    setError(null)
    setErrorAction(null)
    setPreview(null)
    setConfirmed(false)
    setPublished(false)
    publishRequestId.current = requestId()
    setUploadProgress(0)
    try {
      const result = await previewMutation.mutateAsync({
        planId,
        file,
        options: { schema_version: 1, deck_names: [] },
        onUploadProgress: setUploadProgress,
      })
      setPreview(result)
      setUploadProgress(100)
    } catch (cause) {
      setError(safeMessage(cause))
      setErrorAction('preview')
    }
  }

  const publish = async () => {
    if (!preview || !confirmed || publishMutation.isPending) return
    setError(null)
    setErrorAction(null)
    try {
      await publishMutation.mutateAsync({ planId, jobId: preview.job_id, requestId: publishRequestId.current ?? requestId(), options: { schema_version: 1, deck_names: [] } })
      setPublished(true)
    } catch (cause) {
      setError(safeMessage(cause))
      setErrorAction('publish')
    }
  }

  const exportPackage = async () => {
    setError(null)
    try {
      const result = await exportMutation.mutateAsync({ planId, options: { schema_version: 1, deck_names: [] } })
      const response = await import('@/lib/api/study-anki').then(({ studyAnkiApi }) => studyAnkiApi.download(result.download_id))
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'study-plan.apkg'
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(safeMessage(cause))
      setErrorAction(null)
    }
  }

  return (
    <Card className="min-w-0 overflow-hidden" aria-label={t('study.ankiPackagePanel.title')}>
      <CardHeader>
        <CardTitle>{t('study.ankiPackagePanel.title')}</CardTitle>
        <CardDescription>{t('study.ankiPackagePanel.description')}</CardDescription>
      </CardHeader>
      <CardContent className="min-w-0 space-y-5">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <label htmlFor="anki-package-input" className="sr-only">{t('study.ankiPackagePanel.packageLabel')}</label>
          <input id="anki-package-input" type="file" accept=".apkg,application/octet-stream" className="min-w-0 max-w-full text-sm" onChange={(event) => void onFile(event.target.files?.[0])} />
          <Button type="button" variant="outline" onClick={() => void exportPackage()} disabled={exportMutation.isPending}>{exportMutation.isPending ? t('study.ankiPackagePanel.preparingExport') : t('study.ankiPackagePanel.exportPlan')}</Button>
        </div>
        {previewMutation.isPending ? <div className="space-y-2" role="status"><p className="text-sm">{t('study.ankiPackagePanel.uploading')}</p><Progress value={uploadProgress} aria-label={t('study.ankiPackagePanel.uploadProgress')} /></div> : null}
        {error ? <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-destructive"><span>{t(error)}</span><Button type="button" variant="outline" size="sm" onClick={() => {
          if (errorAction === 'preview') void onFile(lastFile.current ?? undefined)
          else if (errorAction === 'publish') void publish()
          else setError(null)
        }}>{errorAction ? t('study.ankiPackagePanel.retry') : t('study.ankiPackagePanel.dismiss')}</Button></div> : null}
        {preview ? (
          <section aria-labelledby="anki-preview-heading" className="min-w-0 space-y-3 rounded-lg border p-4">
            <h3 id="anki-preview-heading" className="font-medium">{t('study.ankiPackagePanel.previewHeading')}</h3>
            <p>{t('study.ankiPackagePanel.previewCounts', { cards: preview.card_count, transformed: preview.transformed_count, rejected: preview.rejected_count })}</p>
            <p className="break-words text-xs text-muted-foreground">{t('study.ankiPackagePanel.packageLine', { sha: preview.package_sha256.slice(0, 12), member: preview.collection_member })}</p>
            {published ? <p role="status" className="text-sm text-primary">{t('study.ankiPackagePanel.imported')}</p> : (
              <div className="space-y-3">
                <label className="flex min-h-11 items-center gap-3 text-sm"><Checkbox checked={confirmed} onCheckedChange={(value) => setConfirmed(value === true)} /> {t('study.ankiPackagePanel.confirmImport')}</label>
                <Button type="button" onClick={() => void publish()} disabled={!confirmed || publishMutation.isPending}>{publishMutation.isPending ? t('study.ankiPackagePanel.importing') : t('study.ankiPackagePanel.importCards')}</Button>
              </div>
            )}
          </section>
        ) : <p className="text-sm text-muted-foreground">{t('study.ankiPackagePanel.chooseFile')}</p>}
      </CardContent>
    </Card>
  )
}
