'use client'

import { markErrorReported } from '@/lib/api/client'
import { useState, useEffect, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Sparkles, Copy, Check, FileText, RefreshCw, AlertCircle } from 'lucide-react'
import { notebooksApi, ExecutiveSynthesisResponse } from '@/lib/api/notebooks'
import { useCreateNote } from '@/lib/hooks/use-notes'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { toast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { RichText } from '@/components/common/RichText'

interface ExecutiveSynthesisDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
  notebookName: string
}

export function ExecutiveSynthesisDialog({
  open,
  onOpenChange,
  notebookId,
  notebookName,
}: ExecutiveSynthesisDialogProps) {
  const { t } = useTranslation()
  const [data, setData] = useState<ExecutiveSynthesisResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const createNote = useCreateNote()

  const fetchSynthesis = useCallback(async () => {
    if (!notebookId) return
    setIsLoading(true)
    setError(null)
    try {
      const res = await notebooksApi.getExecutiveSynthesis(notebookId)
      setData(res)
    } catch (err: unknown) {
      markErrorReported(err) // v0.8.130 — this caller reports the failure itself
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || t('notebooks.executiveSynthesisDialog.generateFailed')
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }, [notebookId, t])

  useEffect(() => {
    setData(null)
    setError(null)
  }, [notebookId])

  useEffect(() => {
    if (open && !data && !isLoading) {
      void fetchSynthesis()
    }
    if (!open) {
      setCopied(false)
    }
  }, [open, data, isLoading, fetchSynthesis])

  const handleCopy = async () => {
    if (!data?.synthesis) return
    try {
      await navigator.clipboard.writeText(data.synthesis)
      setCopied(true)
      toast.success(t('notebooks.executiveSynthesisDialog.copiedToast'))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('notebooks.executiveSynthesisDialog.copyFailed'))
    }
  }

  const handleSaveAsNote = async () => {
    if (!data?.synthesis) return
    setIsSaving(true)
    try {
      await createNote.mutateAsync({
        notebook_id: notebookId,
        title: t('notebooks.executiveSynthesisDialog.noteTitle', { name: notebookName }),
        content: data.synthesis,
      })
      toast.success(t('notebooks.executiveSynthesisDialog.savedToast'))
    } catch {
      // Error handled by useCreateNote
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[88vh] flex flex-col p-6">
        <DialogHeader className="space-y-1.5 pb-2 border-b border-border/40">
          <div className="flex flex-wrap items-center justify-between gap-2 pr-6">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Sparkles className="h-4 w-4" />
              </div>
              <DialogTitle className="text-xl font-semibold">
                {t('notebooks.executiveSynthesisDialog.title')}
              </DialogTitle>
            </div>
            {data && (
              <Badge variant="secondary" className="text-xs bg-primary/15 text-primary border-0 font-medium">
                {t('notebooks.executiveSynthesisDialog.sourcesSynthesized', { count: data.source_count })}
              </Badge>
            )}
          </div>
          <DialogDescription className="text-sm text-muted-foreground">
            <RichText
              text={t('notebooks.executiveSynthesisDialog.description')}
              components={{ name: () => <span className="font-medium text-foreground">{notebookName}</span> }}
            />
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4 pr-1">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-4 text-center">
              <LoadingSpinner className="h-8 w-8 text-primary" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  {t('notebooks.executiveSynthesisDialog.analyzing')}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t('notebooks.executiveSynthesisDialog.evaluating')}
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 space-y-3 text-center">
              <AlertCircle className="h-8 w-8 text-destructive" />
              <p className="text-sm text-destructive font-medium">{error}</p>
              <Button variant="outline" size="sm" onClick={fetchSynthesis}>
                <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                {t('notebooks.executiveSynthesisDialog.retry')}
              </Button>
            </div>
          ) : data ? (
            // v0.8.130 — links use the brand token, not raw blue (UI audit Phase 1)
            <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none space-y-4 prose-headings:font-semibold prose-a:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  h2: ({ children }) => (
                    <h2 className="text-lg font-semibold mt-6 mb-2 border-b border-border/40 pb-1 text-foreground">
                      {children}
                    </h2>
                  ),
                  p: ({ children }) => (
                    <p className="mb-3 leading-6 text-foreground/90">{children}</p>
                  ),
                  ul: ({ children }) => <ul className="mb-3 list-disc pl-5 space-y-1">{children}</ul>,
                  ol: ({ children }) => <ol className="mb-3 list-decimal pl-5 space-y-1">{children}</ol>,
                }}
              >
                {data.synthesis}
              </ReactMarkdown>
            </div>
          ) : null}
        </div>

        <DialogFooter className="flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-4">
          <div className="flex items-center gap-2">
            {data && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={fetchSynthesis}
                disabled={isLoading}
              >
                <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isLoading ? 'animate-spin' : ''}`} />
                {t('notebooks.executiveSynthesisDialog.regenerate')}
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {data && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs gap-1.5"
                  onClick={handleCopy}
                >
                  {copied ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-success-ink" />
                      {t('notebooks.executiveSynthesisDialog.copied')}
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" />
                      {t('notebooks.executiveSynthesisDialog.copySynthesis')}
                    </>
                  )}
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  className="text-xs gap-1.5"
                  onClick={handleSaveAsNote}
                  disabled={isSaving}
                >
                  <FileText className="h-3.5 w-3.5" />
                  {isSaving ? t('notebooks.executiveSynthesisDialog.saving') : t('notebooks.executiveSynthesisDialog.saveAsNote')}
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={() => onOpenChange(false)}
            >
              {t('common.close')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
