import { PodcastStudio } from '@/components/podcasts/PodcastStudio'
import { useLocalModelSettings, useModelRoutePlan } from '@/lib/hooks/use-local-models'

interface KnowledgePodcastPaneProps {
  seedDocumentIds: string[]
}

export function KnowledgePodcastPane({ seedDocumentIds }: KnowledgePodcastPaneProps) {
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
      <PodcastStudio
        seedDocumentIds={seedDocumentIds}
        modelPlans={plans.map(([label, route]) => ({
          label,
          plan: route.data ? {
            outcome: route.data.outcome,
            reason: route.data.route_reason,
          } : undefined,
        }))}
      />
    </section>
  )
}
