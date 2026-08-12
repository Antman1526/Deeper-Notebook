'use client'

import { useState, useRef, useEffect, useMemo } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { LoaderIcon, CheckCircleIcon, XCircleIcon } from 'lucide-react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { WizardContainer, WizardStep } from '@/components/ui/wizard-container'
import {
  SourceTypeStep,
  filesFromInput,
  getOversizedFiles,
  parseAndValidateUrls,
} from './steps/SourceTypeStep'
import { NotebooksStep } from './steps/NotebooksStep'
import { ProcessingStep } from './steps/ProcessingStep'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useTransformations } from '@/lib/hooks/use-transformations'
import { useCreateSource } from '@/lib/hooks/use-sources'
import { useSettings } from '@/lib/hooks/use-settings'
import { CreateSourceRequest } from '@/lib/types/api'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getConfig } from '@/lib/config'

const MAX_BATCH_SIZE = 50

function boundedSourceId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized.length > 0 && normalized.length <= 512 ? normalized : null
}

const createSourceSchema = z.object({
  type: z.enum(['link', 'upload', 'text']),
  title: z.string().optional(),
  url: z.string().optional(),
  content: z.string().optional(),
  file: z.any().optional(),
  notebooks: z.array(z.string()).optional(),
  transformations: z.array(z.string()).optional(),
  embed: z.boolean(),
  async_processing: z.boolean(),
}).refine((data) => {
  if (data.type === 'link') {
    return !!data.url && data.url.trim() !== ''
  }
  if (data.type === 'text') {
    return !!data.content && data.content.trim() !== ''
  }
  if (data.type === 'upload') {
    if (data.file instanceof FileList) {
      return data.file.length > 0
    }
    return !!data.file
  }
  return true
}, {
  message: 'Please provide the required content for the selected source type',
  path: ['type'],
}).refine((data) => {
  // Make title mandatory for text sources
  if (data.type === 'text') {
    return !!data.title && data.title.trim() !== ''
  }
  return true
}, {
  message: 'Title is required for text sources',
  path: ['title'],
})

type CreateSourceFormData = z.infer<typeof createSourceSchema>

interface AddSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultNotebookId?: string
  /** Legacy refresh callback: exactly once after a successful operation. */
  onSourceCreated?: () => void
  /** Receives all bounded IDs exactly once after a successful operation. */
  onSourcesCreated?: (sourceIds: readonly string[]) => void
  // v0.8.77 — files handed in by drag-drop (improvement roadmap, Batch 1).
  // When present and the dialog opens, the upload tab is preselected and these
  // files prefill the file input. Best-effort (see the prefill effect).
  initialFiles?: File[]
}

interface ProcessingState {
  message: string
  progress?: number
}

interface BatchProgress {
  total: number
  completed: number
  failed: number
  currentItem?: string
}

export function AddSourceDialog({
  open,
  onOpenChange,
  defaultNotebookId,
  onSourceCreated,
  onSourcesCreated,
  initialFiles,
}: AddSourceDialogProps) {
  const { t } = useTranslation()

  const WIZARD_STEPS: readonly WizardStep[] = [
    { number: 1, title: t('sources.addSource'), description: t('sources.processDescription') },
    { number: 2, title: t('navigation.notebooks'), description: t('notebooks.searchPlaceholder') },
    { number: 3, title: t('navigation.process'), description: t('sources.processDescription') },
  ]

  // Simplified state management
  const [currentStep, setCurrentStep] = useState(1)
  const [processing, setProcessing] = useState(false)
  const [processingStatus, setProcessingStatus] = useState<ProcessingState | null>(null)
  const [selectedNotebooks, setSelectedNotebooks] = useState<string[]>(
    defaultNotebookId ? [defaultNotebookId] : []
  )
  const [selectedTransformations, setSelectedTransformations] = useState<string[]>([])
  const [sourceUploadMaxBytes, setSourceUploadMaxBytes] = useState<number | null>(null)

  // Batch-specific state
  const [urlValidationErrors, setUrlValidationErrors] = useState<{ url: string; line: number }[]>([])
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null)

  // Cleanup timeouts to prevent memory leaks
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)

  // API hooks
  const createSource = useCreateSource()
  const { data: notebooks = [], isLoading: notebooksLoading } = useNotebooks()
  const { data: transformations = [], isLoading: transformationsLoading } = useTransformations()
  const { data: settings } = useSettings()

  // Form setup
  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors },
    reset,
  } = useForm<CreateSourceFormData>({
    resolver: zodResolver(createSourceSchema),
    defaultValues: {
      notebooks: defaultNotebookId ? [defaultNotebookId] : [],
      embed: settings?.default_embedding_option === 'always' || settings?.default_embedding_option === 'ask',
      async_processing: true,
      transformations: [],
    },
  })

  // Initialize form values when settings and transformations are loaded
  useEffect(() => {
    if (settings && transformations.length > 0) {
      const defaultTransformations = transformations
        .filter(t => t.apply_default)
        .map(t => t.id)

      setSelectedTransformations(defaultTransformations)

      // Reset form with proper embed value based on settings
      const embedValue = settings.default_embedding_option === 'always' ||
                         (settings.default_embedding_option === 'ask')

      reset({
        notebooks: defaultNotebookId ? [defaultNotebookId] : [],
        embed: embedValue,
        async_processing: true,
        transformations: [],
      })
    }
  }, [settings, transformations, defaultNotebookId, reset])

  // v0.8.77 — drag-drop prefill (improvement roadmap, Batch 1). When opened
  // with dropped files, preselect the upload tab and prefill the file input via
  // a DataTransfer-built FileList (the only programmatic way to set an
  // <input type=file>). Graceful: any failure still leaves the dialog on the
  // upload tab for a manual pick. NOTE: this FileList prefill needs a real
  // in-app file-drag test — jsdom/vitest can't fully exercise DataTransfer.
  useEffect(() => {
    if (!open || !initialFiles || initialFiles.length === 0) return
    try {
      setValue('type', 'upload')
      const dt = new DataTransfer()
      for (const f of initialFiles) dt.items.add(f)
      setValue('file', dt.files, { shouldValidate: true })
    } catch {
      try {
        setValue('type', 'upload')
      } catch {
        /* noop — dialog still opens for a manual pick */
      }
    }
  }, [open, initialFiles, setValue])

  // Cleanup effect
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    getConfig()
      .then(config => {
        if (!cancelled) {
          setSourceUploadMaxBytes(config.sourceUploadMaxBytes ?? null)
        }
      })
      .catch(() => {
        if (!cancelled) setSourceUploadMaxBytes(null)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const selectedType = useWatch({ control, name: 'type' })
  const watchedUrl = useWatch({ control, name: 'url' })
  const watchedContent = useWatch({ control, name: 'content' })
  const watchedFile = useWatch({ control, name: 'file' })
  const watchedTitle = useWatch({ control, name: 'title' })

  // Batch mode detection
  const { isBatchMode, itemCount, parsedUrls, parsedFiles } = useMemo(() => {
    let urlCount = 0
    let fileCount = 0
    let parsedUrls: string[] = []
    let parsedFiles: File[] = []

    if (selectedType === 'link' && watchedUrl) {
      const { valid } = parseAndValidateUrls(watchedUrl)
      parsedUrls = valid
      urlCount = valid.length
    }

    if (selectedType === 'upload' && watchedFile) {
      parsedFiles = filesFromInput(watchedFile as FileList | File | undefined)
      if (parsedFiles.length > 0) {
        fileCount = parsedFiles.length
      }
    }

    const isBatchMode = urlCount > 1 || fileCount > 1
    const itemCount = selectedType === 'link' ? urlCount : fileCount

    return { isBatchMode, itemCount, parsedUrls, parsedFiles }
  }, [selectedType, watchedUrl, watchedFile])

  // Check for batch size limit
  const isOverLimit = itemCount > MAX_BATCH_SIZE
  const oversizedFiles = useMemo(
    () => getOversizedFiles(watchedFile as FileList | File | undefined, sourceUploadMaxBytes),
    [watchedFile, sourceUploadMaxBytes],
  )

  // Step validation - now reactive with watched values
  const isStepValid = (step: number): boolean => {
    switch (step) {
      case 1:
        if (!selectedType) return false
        // Check batch size limit
        if (isOverLimit) return false
        // Check for URL validation errors
        if (urlValidationErrors.length > 0) return false

        if (selectedType === 'link') {
          // In batch mode, check that we have at least one valid URL
          if (isBatchMode) {
            return parsedUrls.length > 0
          }
          return !!watchedUrl && watchedUrl.trim() !== ''
        }
        if (selectedType === 'text') {
          return !!watchedContent && watchedContent.trim() !== '' &&
                 !!watchedTitle && watchedTitle.trim() !== ''
        }
        if (selectedType === 'upload') {
          if (oversizedFiles.length > 0) return false
          const files = filesFromInput(watchedFile as FileList | File | undefined)
          return files.length > 0 && files.length <= MAX_BATCH_SIZE
        }
        return true
      case 2:
      case 3:
        return true
      default:
        return false
    }
  }

  // Navigation
  const handleNextStep = (e?: React.MouseEvent) => {
    e?.preventDefault()
    e?.stopPropagation()

    // Validate URLs when leaving step 1 in link mode
    if (currentStep === 1 && selectedType === 'link' && watchedUrl) {
      const { invalid } = parseAndValidateUrls(watchedUrl)
      if (invalid.length > 0) {
        setUrlValidationErrors(invalid)
        return
      }
      setUrlValidationErrors([])
    }

    if (currentStep < 3 && isStepValid(currentStep)) {
      setCurrentStep(currentStep + 1)
    }
  }

  // Clear URL validation errors when user edits
  const handleClearUrlErrors = () => {
    setUrlValidationErrors([])
  }

  const handlePrevStep = (e?: React.MouseEvent) => {
    e?.preventDefault()
    e?.stopPropagation()
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleStepClick = (step: number) => {
    if (step <= currentStep || (step === currentStep + 1 && isStepValid(currentStep))) {
      setCurrentStep(step)
    }
  }

  // Selection handlers
  const handleNotebookToggle = (notebookId: string) => {
    const updated = selectedNotebooks.includes(notebookId)
      ? selectedNotebooks.filter(id => id !== notebookId)
      : [...selectedNotebooks, notebookId]
    setSelectedNotebooks(updated)
  }

  const handleTransformationToggle = (transformationId: string) => {
    const updated = selectedTransformations.includes(transformationId)
      ? selectedTransformations.filter(id => id !== transformationId)
      : [...selectedTransformations, transformationId]
    setSelectedTransformations(updated)
  }

  // Single source submission
  const submitSingleSource = async (data: CreateSourceFormData): Promise<string | null> => {
    const createRequest: CreateSourceRequest = {
      type: data.type,
      notebooks: selectedNotebooks,
      url: data.type === 'link' ? data.url : undefined,
      content: data.type === 'text' ? data.content : undefined,
      title: data.title,
      transformations: selectedTransformations,
      embed: data.embed,
      delete_source: false,
      async_processing: true,
    }

    if (data.type === 'upload' && data.file) {
      const file = data.file instanceof FileList ? data.file[0] : data.file
      const requestWithFile = createRequest as CreateSourceRequest & { file?: File }
      requestWithFile.file = file
    }

    const created = await createSource.mutateAsync(createRequest)
    return boundedSourceId(created?.id)
  }

  // Batch submission
  const submitBatch = async (data: CreateSourceFormData): Promise<{
    success: number
    failed: number
    sourceIds: string[]
  }> => {
    const results = { success: 0, failed: 0, sourceIds: [] as string[] }
    const items: { type: 'url' | 'file'; value: string | File }[] = []

    // Collect items to process
    if (data.type === 'link' && parsedUrls.length > 0) {
      parsedUrls.forEach(url => items.push({ type: 'url', value: url }))
    } else if (data.type === 'upload' && parsedFiles.length > 0) {
      parsedFiles.forEach(file => items.push({ type: 'file', value: file }))
    }

    setBatchProgress({
      total: items.length,
      completed: 0,
      failed: 0,
    })

    // Process each item sequentially
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      const itemLabel = item.type === 'url'
        ? (item.value as string).substring(0, 50) + '...'
        : (item.value as File).name

      setBatchProgress(prev => prev ? {
        ...prev,
        currentItem: itemLabel,
      } : null)

      try {
        const createRequest: CreateSourceRequest = {
          type: item.type === 'url' ? 'link' : 'upload',
          notebooks: selectedNotebooks,
          url: item.type === 'url' ? item.value as string : undefined,
          transformations: selectedTransformations,
          embed: data.embed,
          delete_source: false,
          async_processing: true,
        }

        if (item.type === 'file') {
          const requestWithFile = createRequest as CreateSourceRequest & { file?: File }
          requestWithFile.file = item.value as File
        }

        const created = await createSource.mutateAsync(createRequest)
        const sourceId = boundedSourceId(created?.id)
        if (sourceId) results.sourceIds.push(sourceId)
        results.success++
      } catch (error) {
        console.error(`Error creating source for ${itemLabel}:`, error)
        results.failed++
      }

      setBatchProgress(prev => prev ? {
        ...prev,
        completed: results.success,
        failed: results.failed,
      } : null)
    }

    return results
  }

  const notifySourcesCreated = (sourceIds: readonly string[]) => {
    const boundedIds = sourceIds.slice(0, MAX_BATCH_SIZE)
    onSourceCreated?.()
    onSourcesCreated?.(boundedIds)
  }

  // Form submission
  const onSubmit = async (data: CreateSourceFormData) => {
    try {
      setProcessing(true)

      if (isBatchMode) {
        // Batch submission
        setProcessingStatus({ message: t('sources.processingFiles') })
        const results = await submitBatch(data)

        // Show summary toast
        if (results.failed === 0) {
          toast.success(t('sources.batchSuccess').replace('{count}', results.success.toString()))
        } else if (results.success === 0) {
          toast.error(t('sources.batchFailed').replace('{count}', results.failed.toString()))
        } else {
          toast.warning(t('sources.batchPartial').replace('{success}', results.success.toString()).replace('{failed}', results.failed.toString()))
        }

        if (results.success > 0) notifySourcesCreated(results.sourceIds)
        handleClose()
      } else {
        // Single source submission
        setProcessingStatus({ message: t('sources.submittingSource') })
        const sourceId = await submitSingleSource(data)
        notifySourcesCreated(sourceId ? [sourceId] : [])
        handleClose()
      }
    } catch (error) {
      console.error('Error creating source:', error)
      setProcessingStatus({
        message: t('common.error'),
      })
      timeoutRef.current = setTimeout(() => {
        setProcessing(false)
        setProcessingStatus(null)
        setBatchProgress(null)
      }, 3000)
    }
  }

  const handleFormSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    void handleSubmit(onSubmit)(event)
  }

  // Dialog management
  const handleClose = () => {
    // Clear any pending timeouts
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }

    reset()
    setCurrentStep(1)
    setProcessing(false)
    setProcessingStatus(null)
    setSelectedNotebooks(defaultNotebookId ? [defaultNotebookId] : [])
    setUrlValidationErrors([])
    setBatchProgress(null)

    // Reset to default transformations
    if (transformations.length > 0) {
      const defaultTransformations = transformations
        .filter(t => t.apply_default)
        .map(t => t.id)
      setSelectedTransformations(defaultTransformations)
    } else {
      setSelectedTransformations([])
    }

    onOpenChange(false)
  }

  // Processing view
  if (processing) {
    const progressPercent = batchProgress
      ? Math.round(((batchProgress.completed + batchProgress.failed) / batchProgress.total) * 100)
      : undefined

    return (
      <Dialog open={open} onOpenChange={handleClose}>
        {/* v0.7.25 — added max-h + overflow for long filename lists
            in batch progress views. */}
        <DialogContent className="sm:max-w-[500px] max-h-[85vh] overflow-y-auto" showCloseButton={true}>
          <DialogHeader>
            <DialogTitle>
              {batchProgress ? t('sources.processingFiles') : t('sources.statusProcessing')}
            </DialogTitle>
            <DialogDescription>
              {batchProgress
                ? t('sources.processingBatchSources').replace('{count}', batchProgress.total.toString())
                : t('sources.processingSource')
              }
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="flex items-center gap-3">
              <LoaderIcon className="h-5 w-5 animate-spin text-primary" />
              <span className="text-sm text-muted-foreground">
                {processingStatus?.message || t('common.processing')}
              </span>
            </div>

            {/* Batch progress */}
            {batchProgress && (
              <>
                <div className="w-full bg-muted rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full transition-all duration-300"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5 text-green-600">
                      <CheckCircleIcon className="h-4 w-4" />
                      {batchProgress.completed} {t('common.completed')}
                    </span>
                    {batchProgress.failed > 0 && (
                      <span className="flex items-center gap-1.5 text-destructive">
                        <XCircleIcon className="h-4 w-4" />
                        {batchProgress.failed} {t('common.failed')}
                      </span>
                    )}
                  </div>
                   <span className="text-muted-foreground">
                    {batchProgress.completed + batchProgress.failed} / {batchProgress.total}
                  </span>
                </div>

                {batchProgress.currentItem && (
                  <p className="text-xs text-muted-foreground truncate">
                    {t('common.current')}: {batchProgress.currentItem}
                  </p>
                )}
              </>
            )}

            {/* Single source progress */}
            {!batchProgress && processingStatus?.progress && (
              <div className="w-full bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${processingStatus.progress}%` }}
                />
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  const currentStepValid = isStepValid(currentStep)

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      {/* v0.7.25 — added max-h-[90vh] + flex layout. Without this,
          a long URL list (up to 50) or many validation errors pushed
          the wizard's Next/Done buttons below the fold with no
          scrollbar. Header stays pinned; form body scrolls. */}
      <DialogContent className="sm:max-w-[700px] p-0 max-h-[90vh] flex flex-col">
        <DialogHeader className="px-6 pt-6 pb-0 shrink-0">
          <DialogTitle>{t('sources.addNew')}</DialogTitle>
          <DialogDescription>
            {t('sources.processDescription')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleFormSubmit} className="min-w-0 flex-1 overflow-y-auto">
          <WizardContainer
            currentStep={currentStep}
            steps={WIZARD_STEPS}
            onStepClick={handleStepClick}
            className="border-0"
          >
            {currentStep === 1 && (
              <SourceTypeStep
                // @ts-expect-error - Type inference issue with zod schema
                control={control}
                register={register}
                setValue={setValue}
                // @ts-expect-error - Type inference issue with zod schema
                errors={errors}
                urlValidationErrors={urlValidationErrors}
                onClearUrlErrors={handleClearUrlErrors}
                sourceUploadMaxBytes={sourceUploadMaxBytes}
              />
            )}
            
            {currentStep === 2 && (
              <NotebooksStep
                notebooks={notebooks}
                selectedNotebooks={selectedNotebooks}
                onToggleNotebook={handleNotebookToggle}
                loading={notebooksLoading}
              />
            )}
            
            {currentStep === 3 && (
              <ProcessingStep
                // @ts-expect-error - Type inference issue with zod schema
                control={control}
                transformations={transformations}
                selectedTransformations={selectedTransformations}
                onToggleTransformation={handleTransformationToggle}
                loading={transformationsLoading}
                settings={settings}
              />
            )}
          </WizardContainer>

          {/* Navigation */}
          <div className="flex justify-between items-center px-6 py-4 border-t border-border bg-muted">
            <Button 
              type="button" 
              variant="outline" 
              onClick={handleClose}
            >
              {t('common.cancel')}
            </Button>

            <div className="flex gap-2">
              {currentStep > 1 && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handlePrevStep}
                >
                  {t('common.back')}
                </Button>
              )}

              {/* Show Next button on steps 1 and 2, styled as outline/secondary */}
              {currentStep < 3 && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={(e) => handleNextStep(e)}
                  disabled={!currentStepValid}
                >
                  {t('common.next')}
                </Button>
              )}

              {/* Show Done button on all steps, styled as primary */}
              <Button
                type="submit"
                disabled={!currentStepValid || createSource.isPending}
                className="min-w-[120px]"
              >
                {createSource.isPending ? t('common.adding') : t('common.done')}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
