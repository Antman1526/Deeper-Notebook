'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { TurnIntoPodcastAction } from '@/components/podcasts/TurnIntoPodcastAction'
import { Input } from '@/components/ui/input'
import { useKnowledgeIndexedSearch } from '@/lib/hooks/use-knowledge-command-data'
import { ModelRoutePlanPanel } from '@/components/local-models/ModelRoutePlanPanel'
import { useLocalModelSettings, useModelRoutePlan } from '@/lib/hooks/use-local-models'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

interface KnowledgeSearchPaneProps {
  query: string
  searchMode: 'exact' | 'text' | 'semantic'
  spaceIds: string[]
  authorityKinds: ('app_owned' | 'external_read_only')[]
  onQueryChange?: (query: string) => void
}

export function KnowledgeSearchPane({
  query: initialQuery,
  searchMode,
  spaceIds,
  authorityKinds,
  onQueryChange,
}: KnowledgeSearchPaneProps) {
  const [query, setQuery] = useState(initialQuery)
  const [submitted, setSubmitted] = useState(false)
  const openPodcastReview = usePodcastStudioStore((state) => state.open)
  const indexedSearch = useKnowledgeIndexedSearch(query, submitted, {
    mode: searchMode,
    spaceIds,
    authorityKinds,
    tags: [],
  })
  const results = searchMode === 'semantic'
    ? indexedSearch.semantic.data?.results
    : indexedSearch.text.data?.results
  const settings = useLocalModelSettings()
  const embeddingRoute = useModelRoutePlan(settings.data ? {
    role: 'embedding_retrieval', execution_policy: settings.data.execution_policy, compute_profile: settings.data.compute_profile,
    role_override_model_id: settings.data.role_overrides.embedding_retrieval ?? null, modalities: ['text'],
  } : null)

  const submit = () => {
    if (query.trim().length < 2) return
    setSubmitted(true)
    if (searchMode === 'semantic') indexedSearch.runSemanticSearch()
  }

  return (
    <section aria-label="Knowledge Search" className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Search</h2>
        <p className="text-sm text-muted-foreground">Search is available without a current document selection.</p>
      </div>
      <ModelRoutePlanPanel title="Embedding route" plan={embeddingRoute.data} isError={settings.isError || embeddingRoute.isError} isLoading={settings.isLoading || embeddingRoute.isLoading} />
      <Input
        aria-label="Search knowledge"
        value={query}
        onChange={(event) => {
          const nextQuery = event.target.value
          setQuery(nextQuery)
          onQueryChange?.(nextQuery)
          setSubmitted(false)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit()
        }}
      />
      <Button type="button" onClick={submit} disabled={query.trim().length < 2}>
        Search knowledge
      </Button>
      <TurnIntoPodcastAction
        selection={{
          kind: 'saved_search',
          query: query.trim() || 'search',
          searchMode,
          spaceIds,
          authorityKinds,
        }}
        destination="quick"
        disabledReason={searchMode === 'semantic'
          ? 'Semantic podcast selection needs a verified unified embedding index.'
          : query.trim().length < 2
            ? 'Enter at least two characters to create a podcast from search results.'
            : undefined}
        onOpen={openPodcastReview}
      />
      {results && (
        <ul aria-label="Knowledge search results">
          {results.map((result) => <li key={result.id}>{result.title}</li>)}
        </ul>
      )}
    </section>
  )
}
