interface KnowledgePodcastPaneProps {
  seedDocumentIds: string[]
}

export function KnowledgePodcastPane({ seedDocumentIds }: KnowledgePodcastPaneProps) {
  const selectionLabel = `${seedDocumentIds.length} selected document${seedDocumentIds.length === 1 ? '' : 's'}`

  return (
    <section aria-label="Knowledge Podcast" className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold">Podcast</h2>
        <p className="text-sm text-muted-foreground">{selectionLabel}</p>
      </div>
      <p className="text-sm text-muted-foreground">Podcast generation opens in Phase 2.</p>
    </section>
  )
}
