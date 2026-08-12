'use client'

import { useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { useStudyAnkiExport, useStudyAnkiImportPreview, useStudyAnkiPublish } from '@/lib/hooks/use-study-anki'
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

function safeMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 409) return 'This import changed elsewhere. Review the package again before retrying.'
  if (status === 422) return 'The package could not be read safely. Nothing was imported.'
  if (status === 503) return 'Anki portability is temporarily unavailable. Try again shortly.'
  return 'The package could not be processed. Nothing was changed.'
}

export function AnkiPackagePanel({ planId, lifecycleState = 'approved', enabled = true }: AnkiPackagePanelProps) {
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
        <CardHeader><CardTitle>Anki package portability unavailable</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">Approve the syllabus before importing or exporting a package.</p></CardContent>
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
    <Card className="min-w-0 overflow-hidden" aria-label="Anki package portability">
      <CardHeader>
        <CardTitle>Anki package portability</CardTitle>
        <CardDescription>Preview a bounded package before any native Study cards are changed, or export this approved plan.</CardDescription>
      </CardHeader>
      <CardContent className="min-w-0 space-y-5">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <label htmlFor="anki-package-input" className="sr-only">Anki package</label>
          <input id="anki-package-input" type="file" accept=".apkg,application/octet-stream" className="min-w-0 max-w-full text-sm" onChange={(event) => void onFile(event.target.files?.[0])} />
          <Button type="button" variant="outline" onClick={() => void exportPackage()} disabled={exportMutation.isPending}>{exportMutation.isPending ? 'Preparing export…' : 'Export plan'}</Button>
        </div>
        {previewMutation.isPending ? <div className="space-y-2" role="status"><p className="text-sm">Uploading and inspecting package…</p><Progress value={uploadProgress} aria-label="Upload progress" /></div> : null}
        {error ? <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-destructive"><span>{error}</span><Button type="button" variant="outline" size="sm" onClick={() => {
          if (errorAction === 'preview') void onFile(lastFile.current ?? undefined)
          else if (errorAction === 'publish') void publish()
          else setError(null)
        }}>{errorAction ? 'Retry' : 'Dismiss'}</Button></div> : null}
        {preview ? (
          <section aria-labelledby="anki-preview-heading" className="min-w-0 space-y-3 rounded-lg border p-4">
            <h3 id="anki-preview-heading" className="font-medium">Import preview</h3>
            <p>{preview.card_count} cards ready, {preview.transformed_count} transformed, {preview.rejected_count} rejected</p>
            <p className="break-words text-xs text-muted-foreground">Package {preview.package_sha256.slice(0, 12)}… · {preview.collection_member}</p>
            {published ? <p role="status" className="text-sm text-primary">Cards imported into the native Study deck.</p> : (
              <div className="space-y-3">
                <label className="flex min-h-11 items-center gap-3 text-sm"><Checkbox checked={confirmed} onCheckedChange={(value) => setConfirmed(value === true)} /> Confirm explicit import into this Study Plan</label>
                <Button type="button" onClick={() => void publish()} disabled={!confirmed || publishMutation.isPending}>{publishMutation.isPending ? 'Importing…' : 'Import cards'}</Button>
              </div>
            )}
          </section>
        ) : <p className="text-sm text-muted-foreground">Choose an .apkg file to see transformed and rejected items before publishing.</p>}
      </CardContent>
    </Card>
  )
}
