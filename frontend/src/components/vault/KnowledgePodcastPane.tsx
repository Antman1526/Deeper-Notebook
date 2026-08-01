import { ModelRoutePlanPanel } from '@/components/local-models/ModelRoutePlanPanel'
import { useLocalModelSettings, useModelRoutePlan } from '@/lib/hooks/use-local-models'

interface KnowledgePodcastPaneProps {
  seedDocumentIds: string[]
}

export function KnowledgePodcastPane({ seedDocumentIds }: KnowledgePodcastPaneProps) {
  const selectionLabel = `${seedDocumentIds.length} selected document${seedDocumentIds.length === 1 ? '' : 's'}`
  const settings = useLocalModelSettings()
  const routeRequest = (role: 'evidence_extraction' | 'podcast_outline' | 'podcast_script' | 'claim_verification' | 'text_to_speech', modalities: Array<'text' | 'audio'>) => settings.data ? ({
    role, modalities, execution_policy: settings.data.execution_policy, compute_profile: settings.data.compute_profile,
    role_override_model_id: settings.data.role_overrides[role] ?? null,
  }) : null
  const evidence = useModelRoutePlan(routeRequest('evidence_extraction', ['text']))
  const storyboard = useModelRoutePlan(routeRequest('podcast_outline', ['text']))
  const script = useModelRoutePlan(routeRequest('podcast_script', ['text']))
  const verification = useModelRoutePlan(routeRequest('claim_verification', ['text']))
  const voice = useModelRoutePlan(routeRequest('text_to_speech', ['audio']))
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
        {plans.map(([title, route]) => <ModelRoutePlanPanel key={title} title={title} plan={route.data} isError={settings.isError || route.isError} isLoading={settings.isLoading || route.isLoading} />)}
      </div>
    </section>
  )
}
