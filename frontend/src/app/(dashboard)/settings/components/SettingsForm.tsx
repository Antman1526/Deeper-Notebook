'use client'

import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { useSettings, useUpdateSettings } from '@/lib/hooks/use-settings'
import { useEffect, useState } from 'react'
import { ChevronDownIcon } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
// v0.7.196 — sanitize raw `error.message` (axios stack-trace fragment)
// in the load-failed Alert. Route through ERROR_MAP first; fall back
// to the backend's user-friendly detail string if nothing matches.
import { getApiErrorMessage } from '@/lib/utils/error-handler'

const settingsSchema = z.object({
  default_content_processing_engine_doc: z.enum(['auto', 'docling', 'simple']).optional(),
  // v0.8.68 — added 'crawl4ai' (the v0.8.67u local JS-rendering engine was
  // never selectable here, mirroring the API schema gap fixed this release).
  default_content_processing_engine_url: z.enum(['auto', 'crawl4ai', 'firecrawl', 'jina', 'simple']).optional(),
  default_embedding_option: z.enum(['ask', 'always', 'never']).optional(),
  auto_delete_files: z.enum(['yes', 'no']).optional(),
  // v0.8.68 — forced offline mode (boolean in the API; yes/no in the form
  // to match the existing Select idiom).
  offline_mode: z.enum(['yes', 'no']).optional(),
  // v0.8.88 — opt-in source auto-summary (boolean in the API; yes/no in the
  // form to match the Select idiom).
  auto_summarize_on_ingest: z.enum(['yes', 'no']).optional(),
})

type SettingsFormData = z.infer<typeof settingsSchema>

export function SettingsForm() {
  const { t } = useTranslation()
  const { data: settings, isLoading, error } = useSettings()
  const updateSettings = useUpdateSettings()
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    doc: false,
    url: false,
    embedding: false,
    files: false,
    network: false
  })
  const [hasResetForm, setHasResetForm] = useState(false)
  
  
  const {
    control,
    handleSubmit,
    reset,
    formState: { isDirty }
  } = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      default_content_processing_engine_doc: undefined,
      default_content_processing_engine_url: undefined,
      default_embedding_option: undefined,
      auto_delete_files: undefined,
      offline_mode: undefined,
      auto_summarize_on_ingest: undefined,
    }
  })


  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  useEffect(() => {
    if (settings && settings.default_content_processing_engine_doc && !hasResetForm) {
      const formData = {
        default_content_processing_engine_doc: settings.default_content_processing_engine_doc as 'auto' | 'docling' | 'simple',
        default_content_processing_engine_url: settings.default_content_processing_engine_url as 'auto' | 'crawl4ai' | 'firecrawl' | 'jina' | 'simple',
        default_embedding_option: settings.default_embedding_option as 'ask' | 'always' | 'never',
        auto_delete_files: settings.auto_delete_files as 'yes' | 'no',
        // v0.8.68 — boolean from the API mapped to the form's yes/no idiom.
        offline_mode: (settings.offline_mode ? 'yes' : 'no') as 'yes' | 'no',
        // v0.8.88 — opt-in source auto-summary (default off → 'no').
        auto_summarize_on_ingest: (settings.auto_summarize_on_ingest ? 'yes' : 'no') as 'yes' | 'no',
      }
      reset(formData)
      setHasResetForm(true)
    }
  }, [hasResetForm, reset, settings])

  const onSubmit = async (data: SettingsFormData) => {
    // v0.8.68 — offline_mode is a boolean on the wire; the form keeps the
    // Select-friendly 'yes'/'no' representation.
    const { offline_mode, auto_summarize_on_ingest, ...rest } = data
    await updateSettings.mutateAsync({
      ...rest,
      ...(offline_mode !== undefined
        ? { offline_mode: offline_mode === 'yes' }
        : {}),
      // v0.8.88 — map the form's yes/no back to the API's boolean.
      ...(auto_summarize_on_ingest !== undefined
        ? { auto_summarize_on_ingest: auto_summarize_on_ingest === 'yes' }
        : {}),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('settings.loadFailed')}</AlertTitle>
        <AlertDescription>
          {/* v0.7.196 — `error.message` previously leaked raw axios
              text ("Network Error", "Request failed with status code
              500", Python exception strings via FastAPI's default
              500 handler). getApiErrorMessage routes through the
              translation map first. */}
          {getApiErrorMessage(error, t, 'settings.loadFailed')}
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.contentProcessing')}</CardTitle>
          <CardDescription>
            {t('settings.contentProcessingDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <Label htmlFor="doc_engine">{t('settings.docEngine')}</Label>
            <Controller
              name="default_content_processing_engine_doc"
              control={control}
              render={({ field }) => (
                  <Select
                    key={field.value}
                    name={field.name}
                    value={field.value || ''}
                    onValueChange={field.onChange}
                    disabled={field.disabled || isLoading}
                  >
                      <SelectTrigger id="doc_engine" className="w-full">
                        <SelectValue placeholder={t('settings.docEnginePlaceholder')} />
                      </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">{t('settings.autoRecommended')}</SelectItem>
                      <SelectItem value="docling">{t('settings.docling')}</SelectItem>
                      <SelectItem value="simple">{t('settings.simple')}</SelectItem>
                    </SelectContent>
                  </Select>
              )}
            />
            <Collapsible open={expandedSections.doc} onOpenChange={() => toggleSection('doc')}>
              <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ChevronDownIcon className={`h-4 w-4 transition-transform ${expandedSections.doc ? 'rotate-180' : ''}`} />
                {t('settings.helpMeChoose')}
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground space-y-2">
                <p>{t('settings.docHelp')}</p>
              </CollapsibleContent>
            </Collapsible>
          </div>
          
          <div className="space-y-3">
            <Label htmlFor="url_engine">{t('settings.urlEngine')}</Label>
            <Controller
              name="default_content_processing_engine_url"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="url_engine" className="w-full">
                    <SelectValue placeholder={t('settings.urlEnginePlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">{t('settings.autoRecommended')}</SelectItem>
                    <SelectItem value="crawl4ai">{t('settings.crawl4ai', { defaultValue: 'Crawl4AI (local)' })}</SelectItem>
                    <SelectItem value="firecrawl">{t('settings.firecrawl')}</SelectItem>
                    <SelectItem value="jina">{t('settings.jina')}</SelectItem>
                    <SelectItem value="simple">{t('settings.simple')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
             <Collapsible open={expandedSections.url} onOpenChange={() => toggleSection('url')}>
              <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ChevronDownIcon className={`h-4 w-4 transition-transform ${expandedSections.url ? 'rotate-180' : ''}`} />
                {t('settings.helpMeChoose')}
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground space-y-2">
                <p>{t('settings.urlHelp')}</p>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </CardContent>
      </Card>

       <Card>
        <CardHeader>
          <CardTitle>{t('settings.embeddingAndSearch')}</CardTitle>
          <CardDescription>
            {t('settings.embeddingAndSearchDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
           <div className="space-y-3">
            <Label htmlFor="embedding">{t('settings.defaultEmbeddingOption')}</Label>
            <Controller
              name="default_embedding_option"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="embedding" className="w-full">
                    <SelectValue placeholder={t('settings.embeddingOptionPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ask">{t('settings.ask')}</SelectItem>
                    <SelectItem value="always">{t('settings.always')}</SelectItem>
                    <SelectItem value="never">{t('settings.never')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
             <Collapsible open={expandedSections.embedding} onOpenChange={() => toggleSection('embedding')}>
              <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ChevronDownIcon className={`h-4 w-4 transition-transform ${expandedSections.embedding ? 'rotate-180' : ''}`} />
                {t('settings.helpMeChoose')}
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground space-y-2">
                <p>{t('settings.embeddingHelp')}</p>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </CardContent>
      </Card>

       <Card>
        <CardHeader>
          <CardTitle>{t('settings.fileManagement')}</CardTitle>
          <CardDescription>
            {t('settings.fileManagementDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
           <div className="space-y-3">
            <Label htmlFor="auto_delete">{t('settings.autoDeleteFiles')}</Label>
            <Controller
              name="auto_delete_files"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="auto_delete" className="w-full">
                    <SelectValue placeholder={t('settings.autoDeletePlaceholder')} />
                  </SelectTrigger>
                   <SelectContent>
                    <SelectItem value="yes">{t('common.yes')}</SelectItem>
                    <SelectItem value="no">{t('common.no')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
             <Collapsible open={expandedSections.files} onOpenChange={() => toggleSection('files')}>
              <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ChevronDownIcon className={`h-4 w-4 transition-transform ${expandedSections.files ? 'rotate-180' : ''}`} />
                {t('settings.helpMeChoose')}
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground space-y-2">
                <p>{t('settings.filesHelp')}</p>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </CardContent>
      </Card>

      {/* v0.8.88 — opt-in source auto-summary (improvement roadmap, Batch 4). */}
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.sources', { defaultValue: 'Sources' })}</CardTitle>
          <CardDescription>
            {t('settings.sourcesDesc', { defaultValue: 'Options applied when sources are added.' })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <Label htmlFor="auto_summarize">
              {t('settings.autoSummarize', { defaultValue: 'Automatically summarize sources on import' })}
            </Label>
            <Controller
              name="auto_summarize_on_ingest"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="auto_summarize" className="w-full">
                    <SelectValue placeholder={t('common.no')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yes">{t('common.yes')}</SelectItem>
                    <SelectItem value="no">{t('common.no')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
            <p className="text-sm text-muted-foreground">
              {t('settings.autoSummarizeHelp', {
                defaultValue:
                  'When on, each source you add gets a short AI summary (one extra LLM call per source). It appears on the source card and in the source’s insights.',
              })}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.network', { defaultValue: 'Network' })}</CardTitle>
          <CardDescription>
            {t('settings.networkDesc', { defaultValue: 'Control whether the app may use the internet.' })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <Label htmlFor="offline_mode">{t('settings.offlineMode', { defaultValue: 'Offline mode' })}</Label>
            <Controller
              name="offline_mode"
              control={control}
              render={({ field }) => (
                <Select
                  key={field.value}
                  name={field.name}
                  value={field.value || ''}
                  onValueChange={field.onChange}
                  disabled={field.disabled || isLoading}
                >
                  <SelectTrigger id="offline_mode" className="w-full">
                    <SelectValue placeholder={t('settings.offlineModePlaceholder', { defaultValue: 'Off' })} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yes">{t('common.yes')}</SelectItem>
                    <SelectItem value="no">{t('common.no')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
            <Collapsible open={expandedSections.network} onOpenChange={() => toggleSection('network')}>
              <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ChevronDownIcon className={`h-4 w-4 transition-transform ${expandedSections.network ? 'rotate-180' : ''}`} />
                {t('settings.helpMeChoose')}
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground space-y-2">
                <p>{t('settings.offlineModeHelp', { defaultValue: 'Never use the internet. Cloud models, web search, and email digests are disabled; local models keep working.' })}</p>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
         <Button
          type="submit"
          disabled={!isDirty || updateSettings.isPending}
        >
          {updateSettings.isPending ? t('common.saving') : t('common.save')}
        </Button>
      </div>
    </form>
  )
}
