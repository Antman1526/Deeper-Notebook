import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { ModelRoutePlan } from '@/lib/api/local-models'

const label = (value: string) => value.replace(/_/g, ' ')

export function ModelRoutePlanPanel({ title, plan, isLoading = false, isError = false }: { title: string; plan?: ModelRoutePlan; isLoading?: boolean; isError?: boolean }) {
  const outcome = plan?.outcome === 'ready' ? 'Ready' : plan?.outcome === 'approval_required' ? 'Approval required' : 'Blocked'
  return <Card data-testid={`route-plan-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
    <CardHeader className="pb-3"><CardTitle className="text-base">{title}</CardTitle><CardDescription>Explainable, redacted selection facts. Paths, prompts, and source text stay out of route plans.</CardDescription></CardHeader>
    <CardContent className="space-y-2 text-sm">
      {isLoading ? <p className="text-muted-foreground">Planning local route…</p> : isError ? <p role="status" className="text-muted-foreground">Route plan is unavailable. No fallback was selected.</p> : !plan ? <p className="text-muted-foreground">No route planned yet.</p> : <>
        <Badge variant={plan.outcome === 'ready' ? 'secondary' : 'outline'}>{outcome}</Badge>
        <p>{plan.route_reason}</p>
        {plan.selected_model_id && <p><span className="text-muted-foreground">Selected model: </span><code>{plan.selected_model_id}</code>{plan.resource_tier ? ` · ${label(plan.resource_tier)} tier` : ''}</p>}
        {plan.selection_source && <p className="text-xs text-muted-foreground">Selection: {label(plan.selection_source)}</p>}
        {plan.blocked_reason && <p role="status" className="text-sm text-destructive">{plan.blocked_reason}</p>}
        {plan.escalation_model_ids.length > 0 && <p className="text-xs text-muted-foreground">Eligible escalation: {plan.escalation_model_ids.join(', ')}</p>}
      </>}
    </CardContent>
  </Card>
}
