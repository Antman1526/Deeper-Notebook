'use client'

/**
 * v0.8.68 — SkillOpt prompt optimizer dialog (microsoft/SkillOpt, MIT).
 *
 * Flow: pick a notebook → its recent sources become training examples →
 * describe what a good output looks like → run. The backend trains the
 * transformation's prompt as a SkillOpt "skill document" (rollout →
 * LLM-judge scoring → validation-gated edits) and returns an optimized
 * prompt the user reviews and applies. Nothing is applied automatically.
 */

import { useEffect, useRef, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'

import { transformationsApi } from '@/lib/api/transformations'
import { sourcesApi } from '@/lib/api/sources'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useUpdateTransformation } from '@/lib/hooks/use-transformations'
import { useTranslation } from '@/lib/hooks/use-translation'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

interface Transformation {
  id: string
  name: string
  title: string
  description: string
  prompt: string
  apply_default: boolean
}

interface OptimizePromptDialogProps {
  transformation: Transformation | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

type Phase = 'configure' | 'running' | 'review' | 'failed'

export function OptimizePromptDialog({
  transformation,
  open,
  onOpenChange,
}: OptimizePromptDialogProps) {
  const { t } = useTranslation()
  const { data: notebooks } = useNotebooks()
  const updateTransformation = useUpdateTransformation()

  const [phase, setPhase] = useState<Phase>('configure')
  const [notebookId, setNotebookId] = useState('')
  const [criteria, setCriteria] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [optimized, setOptimized] = useState<string | null>(null)
  const [changed, setChanged] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!open) {
      setPhase('configure')
      setError(null)
      setOptimized(null)
      setElapsed(0)
      if (pollRef.current) clearInterval(pollRef.current)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [open])

  if (!transformation) return null

  const start = async () => {
    setError(null)
    try {
      // Use the notebook's most recent sources as training examples.
      const sources = await sourcesApi.list({
        notebook_id: notebookId,
        limit: 6,
        sort_by: 'updated',
      })
      const ids = (sources ?? [])
        .map((s: { id: string }) => s.id)
        .slice(0, 6)
      if (ids.length < 2) {
        setError(
          t('transformations.optimizeNeedsSources', {
            defaultValue:
              'This notebook needs at least 2 processed sources to use as examples.',
          }),
        )
        return
      }
      const { job_id } = await transformationsApi.optimizePrompt(
        transformation.id,
        { source_ids: ids, criteria: criteria.trim() },
      )
      setPhase('running')
      const startedAt = Date.now()
      pollRef.current = setInterval(async () => {
        setElapsed(Math.round((Date.now() - startedAt) / 1000))
        try {
          const job = await transformationsApi.getOptimizeJob(job_id)
          const status = (job.status || '').toLowerCase()
          if (status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current)
            setOptimized(job.result?.optimized_prompt ?? null)
            setChanged(Boolean(job.result?.changed))
            setPhase('review')
          } else if (status === 'failed' || status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current)
            setError(job.error_message || 'Optimization failed')
            setPhase('failed')
          }
        } catch {
          /* transient poll errors — keep polling */
        }
      }, 5000)
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? String(e)
      setError(detail)
    }
  }

  const apply = async () => {
    if (!optimized) return
    await updateTransformation.mutateAsync({
      id: transformation.id,
      data: { ...transformation, prompt: optimized },
    })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(90vw,720px)] max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            {t('transformations.optimizeTitle', {
              defaultValue: 'Optimize prompt',
            })}{' '}
            — {transformation.title}
          </DialogTitle>
          <DialogDescription>
            {t('transformations.optimizeDesc', {
              defaultValue:
                'Trains this prompt against example sources from a notebook (powered by Microsoft SkillOpt). Edits are only kept when they improve held-out results. You review before anything is applied.',
            })}
          </DialogDescription>
        </DialogHeader>

        {phase === 'configure' && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{t('transformations.optimizeNotebook', { defaultValue: 'Example notebook' })}</Label>
              <Select value={notebookId} onValueChange={setNotebookId}>
                <SelectTrigger className="w-full">
                  <SelectValue
                    placeholder={t('transformations.optimizeNotebookPlaceholder', {
                      defaultValue: 'Pick a notebook whose sources represent typical inputs',
                    })}
                  />
                </SelectTrigger>
                <SelectContent>
                  {(notebooks ?? []).map((nb: { id: string; name: string }) => (
                    <SelectItem key={nb.id} value={nb.id}>
                      {nb.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t('transformations.optimizeCriteria', { defaultValue: 'What does a good output look like?' })}</Label>
              <Textarea
                value={criteria}
                onChange={(e) => setCriteria(e.target.value)}
                placeholder={t('transformations.optimizeCriteriaPlaceholder', {
                  defaultValue:
                    'e.g. Under 150 words, leads with the key finding, plain language, never invents facts not in the source.',
                })}
                className="min-h-[100px] text-xs"
              />
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
            <div className="flex justify-end">
              <Button
                onClick={start}
                disabled={!notebookId || criteria.trim().length < 10}
              >
                <Sparkles className="mr-2 h-4 w-4" />
                {t('transformations.optimizeStart', { defaultValue: 'Start optimization' })}
              </Button>
            </div>
          </div>
        )}

        {phase === 'running' && (
          <div className="flex flex-col items-center gap-3 py-10">
            <Loader2 className="h-6 w-6 animate-spin" />
            <p className="text-sm text-muted-foreground">
              {t('transformations.optimizeRunning', {
                defaultValue:
                  'Optimizing — running rollouts, judging outputs, testing edits…',
              })}
            </p>
            <p className="text-xs text-muted-foreground">{elapsed}s</p>
          </div>
        )}

        {phase === 'failed' && (
          <div className="space-y-3 py-4">
            <p className="text-sm text-destructive whitespace-pre-wrap">{error}</p>
            <Button variant="outline" size="sm" onClick={() => setPhase('configure')}>
              {t('common.back')}
            </Button>
          </div>
        )}

        {phase === 'review' && (
          <div className="flex-1 flex flex-col gap-3 overflow-hidden">
            {!changed && (
              <p className="text-xs text-muted-foreground">
                {t('transformations.optimizeNoChange', {
                  defaultValue:
                    'No edit beat the original on the validation set — your prompt held up. Try different criteria or examples.',
                })}
              </p>
            )}
            <ScrollArea className="flex-1">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label className="text-xs">{t('transformations.optimizeOriginal', { defaultValue: 'Current prompt' })}</Label>
                  <pre className="rounded border bg-muted/20 p-2 text-[11px] whitespace-pre-wrap">
                    {transformation.prompt}
                  </pre>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{t('transformations.optimizeResult', { defaultValue: 'Optimized prompt' })}</Label>
                  <pre className="rounded border border-emerald-500/40 bg-emerald-500/5 p-2 text-[11px] whitespace-pre-wrap">
                    {optimized}
                  </pre>
                </div>
              </div>
            </ScrollArea>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                {t('transformations.optimizeDiscard', { defaultValue: 'Discard' })}
              </Button>
              <Button
                size="sm"
                onClick={apply}
                disabled={!changed || !optimized || updateTransformation.isPending}
              >
                {t('transformations.optimizeApply', { defaultValue: 'Apply optimized prompt' })}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
