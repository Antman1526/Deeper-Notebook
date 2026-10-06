import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { ModelRoutePlan } from '@/lib/api/local-models'
import { MODEL_RESOURCE_TIER_KEYS, MODEL_SELECTION_SOURCE_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'

export function ModelRoutePlanPanel({ title, routeId, plan, isLoading = false, isError = false }: { title: string; routeId: 'research-chat-route' | 'embedding-route'; plan?: ModelRoutePlan; isLoading?: boolean; isError?: boolean }) {
  const { t } = useTranslation()
  const outcome = plan?.outcome === 'ready' ? t('settings.modelRoutePlanPanel.outcomeReady') : plan?.outcome === 'approval_required' ? t('settings.modelRoutePlanPanel.outcomeApprovalRequired') : t('settings.modelRoutePlanPanel.outcomeBlocked')
  return <Card data-testid={`route-plan-${routeId}`}>
    <CardHeader className="pb-3"><CardTitle className="text-base">{title}</CardTitle><CardDescription>{t('settings.modelRoutePlanPanel.description')}</CardDescription></CardHeader>
    <CardContent className="space-y-2 text-sm">
      {isLoading ? <p className="text-muted-foreground">{t('settings.modelRoutePlanPanel.planning')}</p> : isError ? <p role="status" className="text-muted-foreground">{t('settings.modelRoutePlanPanel.unavailable')}</p> : !plan ? <p className="text-muted-foreground">{t('settings.modelRoutePlanPanel.noRoute')}</p> : <>
        <Badge variant={plan.outcome === 'ready' ? 'secondary' : 'outline'}>{outcome}</Badge>
        <p>{plan.route_reason}</p>
        {plan.selected_model_id && <p><span className="text-muted-foreground">{t('settings.modelRoutePlanPanel.selectedModel')}{' '}</span><code>{plan.selected_model_id}</code>{plan.resource_tier ? ` · ${t('settings.modelRoutePlanPanel.tierSuffix', { tier: enumLabel(t, MODEL_RESOURCE_TIER_KEYS, plan.resource_tier, spacedEnum(plan.resource_tier)) })}` : ''}</p>}
        {plan.selection_source && <p className="text-xs text-muted-foreground">{t('settings.modelRoutePlanPanel.selection', { source: enumLabel(t, MODEL_SELECTION_SOURCE_KEYS, plan.selection_source, spacedEnum(plan.selection_source)) })}</p>}
        {plan.blocked_reason && <p role="status" className="text-sm text-destructive">{plan.blocked_reason}</p>}
        {plan.escalation_model_ids.length > 0 && <p className="text-xs text-muted-foreground">{t('settings.modelRoutePlanPanel.eligibleEscalation', { models: plan.escalation_model_ids.join(', ') })}</p>}
      </>}
    </CardContent>
  </Card>
}
