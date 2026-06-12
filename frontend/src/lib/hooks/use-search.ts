import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'
// v0.7.199 — getApiErrorKey returns a raw i18n key. Direct use as
// toast description renders the key as text on mapped errors. Use
// getApiErrorMessage which returns the translated string (or backend
// detail when no mapping exists). Missed in the v0.7.196 sweep
// because this file is a single hook, not in the use-credentials /
// use-podcasts / use-notes / use-models cluster.
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { searchApi } from '@/lib/api/search'
import { SearchRequest } from '@/lib/types/search'

export function useSearch() {
  const { t } = useTranslation()
  return useMutation({
    mutationFn: async (params: SearchRequest) => {
      const response = await searchApi.search(params)

      // Process results to add final_score
      const processedResults = response.results.map(result => ({
        ...result,
        final_score: result.relevance ?? result.similarity ?? result.score ?? 0
      }))

      // Sort by final_score descending
      processedResults.sort((a, b) => b.final_score - a.final_score)

      return {
        ...response,
        results: processedResults
      }
    },
    onError: (error: unknown) => {
      // v0.7.199 — was `t(getApiErrorKey(error.message))` which, for
      // unmapped errors, returned the raw backend message string
      // wrapped in t() — which then returned the message itself
      // verbatim, leaking axios/FastAPI stack-trace fragments into
      // the toast.
      toast.error(t('apiErrors.searchFailed'), {
        description: getApiErrorMessage(error, t, 'apiErrors.genericError'),
      })
    }
  })
}
