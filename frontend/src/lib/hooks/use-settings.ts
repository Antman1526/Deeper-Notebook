import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi } from '@/lib/api/settings'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { SettingsResponse } from '@/lib/types/api'

export function useSettings() {
  return useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => settingsApi.get(),
  })
}

// v0.7.136 — Hook for the read-only observability snapshot. Separate
// query key so it doesn't get invalidated when writable settings
// change (the underlying values come from env, not from /settings
// mutations). `refetchOnWindowFocus: true` so a tab-switch after
// editing .env shows the new values without a manual refresh.
export function useObservabilitySettings() {
  return useQuery({
    queryKey: QUERY_KEYS.observabilitySettings,
    queryFn: () => settingsApi.getObservability(),
    refetchOnWindowFocus: true,
  })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: Partial<SettingsResponse>) => settingsApi.update(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settings })
      toast({
        title: t('common.success'),
        description: t('common.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key), 'common.error'),
        variant: 'destructive',
      })
    },
  })
}