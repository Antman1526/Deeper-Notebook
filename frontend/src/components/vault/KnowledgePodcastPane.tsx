import { ModelRoutePlanPanel } from '@/components/local-models/ModelRoutePlanPanel'
import { useModelRoutePlan } from '@/lib/hooks/use-local-models'

interface KnowledgePodcastPaneProps {
  seedDocumentIds: string[]
}

export function KnowledgePodcastPane({ seedDocumentIds }: KnowledgePodcastPaneProps) {
  const selectionLabel = `${seedDocumentIds.length} selected document${seedDocumentIds.length === 1 ? '' : 's'}`
  const evidence = useModelRoutePlan({ role: 'evidence_extraction', execution_policy: 'strict_local', compute_profile: 'balanced', modalities: ['text'] })
  const storyboard = useModelRoutePlan({ role: 'podcast_outline', execution_policy: 'strict_local', compute_profile: 'balanced', modalities: ['text'] })
  const script = useModelRoutePlan({ role: 'podcast_script', execution_policy: 'strict_local', compute_profile: 'balanced', modalities: ['text'] })
  const verification = useModelRoutePlan({ role: 'claim_verification', execution_policy: 'strict_local', compute_profile: 'balanced', modalities: ['text'] })
  const voice = useModelRoutePlan({ role: 'text_to_speech', execution_policy: 'strict_local', compute_profile: 'balanced', modalities: ['audio'] })
  const plans = [
    ['Evidence route', evidence], ['Storyboard route', storyboard], ['Script route', script], ['Verification route', verification], ['Voice route', voice],
  ] as const

  return (
    <section aria-label="Knowledge Podcast" className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold">Podcast</h2>
        <p className="text-sm text-muted-foreground">{selectionLabel}</p>
      </div>
      <p className="text-sm text-muted-foreground">Podcast generation opens in Phase 2.</p>
      <div className="grid gap-3 lg:grid-cols-2">
        {plans.map(([title, route]) => <ModelRoutePlanPanel key={title} title={title} plan={route.data} isError={route.isError} isLoading={route.isLoading} />)}
      </div>
    </section>
  )
}
