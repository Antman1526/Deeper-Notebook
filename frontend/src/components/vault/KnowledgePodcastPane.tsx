'use client'

import dynamic from 'next/dynamic'
import { useLocalModelSettings, useModelRoutePlan } from '@/lib/hooks/use-local-models'
import type { ModelRoutePlan } from '@/lib/api/local-models'

type StudioRouteRole = 'podcast_outline' | 'podcast_script' | 'text_to_speech' | 'speech_to_text'
function isStudioRouteRole(role: ModelRoutePlan['role']): role is StudioRouteRole {
  return role === 'podcast_outline' || role === 'podcast_script' || role === 'text_to_speech' || role === 'speech_to_text'
}

const LazyPodcastStudio = dynamic(
  () => import('@/components/podcasts/PodcastStudio').then((module) => module.PodcastStudio),
  {
    ssr: false,
    loading: () => (
      <section aria-label="Podcast Intelligence Studio" className="rounded-md border p-4" aria-busy="true">
        <p className="text-sm text-muted-foreground">Loading Podcast Intelligence Studio…</p>
      </section>
    ),
  },
)

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
      <LazyPodcastStudio
        seedDocumentIds={seedDocumentIds}
        modelPlans={plans.map(([label, route]) => ({
          label,
          overrideChoices: route.data && isStudioRouteRole(route.data.role) && route.data.role !== 'speech_to_text'
            ? [route.data.selected_model_id, ...route.data.escalation_model_ids].filter((modelId): modelId is string => Boolean(modelId))
            : [],
          plan: route.data ? {
            outcome: route.data.outcome,
            reason: route.data.route_reason,
            role: isStudioRouteRole(route.data.role) ? route.data.role : undefined,
            modelId: route.data.selected_model_id,
            provider: route.data.selected_provider,
            resourceTier: route.data.resource_tier,
            selectionSource: route.data.selection_source,
          } : undefined,
        }))}
      />
    </section>
  )
}
