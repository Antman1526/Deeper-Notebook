import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { modelsApi } from '@/lib/api/models'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
// v0.7.196 — use the translating variant (getApiErrorMessage) so toast
// descriptions show the localised message string, not the raw i18n key.
// getApiErrorKey returns "apiErrors.notebookNotFound" as a literal —
// when passed straight into a toast description without an outer t(),
// the user sees the key string rendered as text. v0.7.196 swept this
// across the hook layer.
import { getApiErrorKey, getApiErrorMessage } from '@/lib/utils/error-handler'
import { CreateModelRequest, ModelDefaults, ModelTestResult } from '@/lib/types/models'

export const MODEL_QUERY_KEYS = {
  models: ['models'] as const,
  model: (id: string) => ['models', id] as const,
  defaults: ['models', 'defaults'] as const,
  providers: ['models', 'providers'] as const,
}

export function useModels() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.models,
    queryFn: () => modelsApi.list(),
  })
}

export function useModel(id: string) {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.model(id),
    queryFn: () => modelsApi.get(id),
    enabled: !!id,
  })
}

export function useCreateModel() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateModelRequest) => modelsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      toast({
        title: t('common.success'),
        description: t('models.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'common.error'),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteModel() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => modelsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })
      queryClient.invalidateQueries({ queryKey: ['credentials'] })
      toast({
        title: t('common.success'),
        description: t('models.deleteSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'common.error'),
        variant: 'destructive',
      })
    },
  })
}

export function useModelDefaults() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.defaults,
    queryFn: () => modelsApi.getDefaults(),
  })
}

export function useUpdateModelDefaults() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: Partial<ModelDefaults>) => modelsApi.updateDefaults(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })
      toast({
        title: t('common.success'),
        description: t('models.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'common.error'),
        variant: 'destructive',
      })
    },
  })
}

export function useProviders() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.providers,
    queryFn: () => modelsApi.getProviders(),
  })
}

/**
 * ONP v0.5.2 — capability-aware re-evaluation hook. Wired to the
 * "Re-evaluate model assignments" button in the api-keys settings page.
 * Uses our local-model scoring engine; `force=true` overrides previous
 * picks (useful when the user has just downloaded a new model).
 */
export function useAutoAssignCapability() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ force }: { force?: boolean } = {}) =>
      modelsApi.autoAssignCapability(force ?? false),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })
      const assignedCount = Object.keys(result.assigned).length
      const missingCount = result.missing.length
      if (assignedCount > 0) {
        toast({
          title: t('common.success'),
          description: `Re-evaluated ${assignedCount} slot${assignedCount === 1 ? '' : 's'}` +
            (missingCount > 0 ? ` (${missingCount} slot${missingCount === 1 ? '' : 's'} have no eligible model)` : ''),
        })
      } else if (missingCount > 0) {
        toast({
          title: 'No changes',
          description: `${missingCount} slot${missingCount === 1 ? ' has' : 's have'} no eligible model.`,
        })
      } else {
        toast({
          title: 'No changes',
          description: 'All slots are already assigned. Use Reset to force re-evaluation.',
        })
      }
    },
    onError: (error: unknown) => {
      // v0.7.196 — was `error.message` raw — surfaces backend stack-trace
      // text in the toast. getApiErrorMessage routes through ERROR_MAP
      // first, falling back to the backend-provided detail string only
      // when it's user-friendly.
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'common.error'),
        variant: 'destructive',
      })
    },
  })
}


export function useAutoAssignDefaults() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: () => modelsApi.autoAssign(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })

      const assignedCount = Object.keys(result.assigned).length
      const missingCount = result.missing.length

      if (assignedCount > 0) {
        toast({
          title: t('common.success'),
          description: t('models.autoAssignSuccess').replace('{count}', assignedCount.toString()),
        })
      } else if (missingCount > 0) {
        toast({
          title: t('common.warning'),
          description: t('models.autoAssignNoModels'),
          variant: 'destructive',
        })
      } else {
        toast({
          title: t('common.success'),
          description: t('models.autoAssignAlreadySet'),
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, t, 'common.error'),
        variant: 'destructive',
      })
    },
  })
}

export function useTestModel() {
  const { t } = useTranslation()
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null)
  const [testedModelName, setTestedModelName] = useState('')
  const [testingModelId, setTestingModelId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (modelId: string) => modelsApi.testModel(modelId),
    onSuccess: (result) => {
      setTestResult(result)
      setTestingModelId(null)
    },
    onError: (error: unknown) => {
      // v0.7.196 — `String(error)` would surface "[object Object]" or
      // raw axios `Error: Network Error` text in the result strip the
      // user sees. Route via getApiErrorMessage so the user sees the
      // translated mapped message, or the backend's user-friendly
      // detail string if no mapping exists.
      const msg = getApiErrorMessage(error, t, 'common.error')
      setTestResult({ success: false, message: msg })
      setTestingModelId(null)
    },
  })

  const testModel = useCallback((modelId: string, modelName: string) => {
    setTestedModelName(modelName)
    setTestingModelId(modelId)
    setTestResult(null)
    mutation.mutate(modelId)
  }, [mutation])

  const clearResult = useCallback(() => {
    setTestResult(null)
    setTestedModelName('')
    setTestingModelId(null)
  }, [])

  return {
    testModel,
    isPending: mutation.isPending,
    testingModelId,
    testResult,
    testedModelName,
    clearResult,
  }
}
