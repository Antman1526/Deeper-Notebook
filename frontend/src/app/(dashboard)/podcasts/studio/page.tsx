'use client'

import { AppShell } from '@/components/layout/AppShell'
import { PodcastStudio } from '@/components/podcasts/PodcastStudio'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

/** Route counterpart to the Knowledge-pane Studio; selections remain transient. */
export default function PodcastStudioPage() {
  const selections = usePodcastStudioStore((state) => state.selections)
  const seedDocumentIds = selections.flatMap(selection => (
    selection.kind === 'knowledge_document' ? [selection.documentId]
      : selection.kind === 'graph_selection' ? selection.documentIds
        : []
  ))

  return (
    <AppShell>
      <main className="flex-1 overflow-y-auto px-6 py-10 sm:px-8">
        <PodcastStudio seedDocumentIds={[...new Set(seedDocumentIds)]} selections={selections} />
      </main>
    </AppShell>
  )
}
