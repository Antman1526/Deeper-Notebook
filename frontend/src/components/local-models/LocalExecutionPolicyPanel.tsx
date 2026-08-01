'use client'

import { useState } from 'react'

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { LocalModelSettings } from '@/lib/api/local-models'

type Props = {
  policy: LocalModelSettings['execution_policy']
  computeProfile: LocalModelSettings['compute_profile']
  memoryLimitBytes: number | null
  cloudRouteRequested?: boolean
  isSaving?: boolean
  onSave: (next: Pick<LocalModelSettings, 'execution_policy' | 'compute_profile' | 'local_model_memory_limit_bytes'>) => void
}

const labels = { strict_local: 'Strict Local', local_preferred: 'Local Preferred', custom: 'Custom' } as const

export function LocalExecutionPolicyPanel({ policy, computeProfile, memoryLimitBytes, cloudRouteRequested = false, isSaving, onSave }: Props) {
  const [nextPolicy, setNextPolicy] = useState(policy)
  const [nextProfile, setNextProfile] = useState(computeProfile)
  const [nextLimit, setNextLimit] = useState(memoryLimitBytes?.toString() ?? '0')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [stage, setStage] = useState('research chat')
  const [contentClass, setContentClass] = useState('selected knowledge')
  const strictBlocksCloud = nextPolicy === 'strict_local' && cloudRouteRequested
  const limit = Number(nextLimit)
  const validLimit = Number.isSafeInteger(limit) && limit >= 0

  const choosePolicy = (value: LocalModelSettings['execution_policy']) => {
    if (value === 'local_preferred' && nextPolicy !== 'local_preferred') {
      setConfirmOpen(true)
      return
    }
    setNextPolicy(value)
  }
  const confirmLocalPreferred = () => {
    setNextPolicy('local_preferred')
    setConfirmOpen(false)
  }

  return <Card data-testid="local-execution-policy">
    <CardHeader className="pb-3"><CardTitle className="text-base">Local execution policy</CardTitle><CardDescription>Strict Local never contacts cloud endpoints. Local Preferred requires a contextual confirmation before any cloud route.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Execution policy">
        {(Object.keys(labels) as LocalModelSettings['execution_policy'][]).map(value => <Button key={value} type="button" variant={nextPolicy === value ? 'default' : 'outline'} onClick={() => choosePolicy(value)}>
          {value === 'local_preferred' ? 'Use Local Preferred' : labels[value]}
        </Button>)}
      </div>
      {strictBlocksCloud && <p role="alert" className="text-sm text-destructive">Strict Local blocks cloud routes.</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium">Compute profile<select aria-label="Compute profile" className="mt-1 w-full rounded-md border bg-background p-2" value={nextProfile} onChange={event => setNextProfile(event.target.value as LocalModelSettings['compute_profile'])}><option value="efficient">Efficient</option><option value="balanced">Balanced</option><option value="maximum_quality">Maximum quality</option></select></label>
        <label className="text-sm font-medium">Memory limit (bytes)<Input aria-label="Memory limit bytes" className="mt-1" inputMode="numeric" min="0" onChange={event => setNextLimit(event.target.value)} value={nextLimit} /></label>
      </div>
      <Button type="button" disabled={Boolean(isSaving) || strictBlocksCloud || !validLimit} onClick={() => onSave({ execution_policy: nextPolicy, compute_profile: nextProfile, local_model_memory_limit_bytes: limit })}>Save local execution policy</Button>
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Confirm a Local Preferred cloud route</AlertDialogTitle><AlertDialogDescription>Identify the exact stage and content class before Local Preferred can proceed to a cloud model. This confirmation does not run a task.</AlertDialogDescription></AlertDialogHeader>
          <label className="text-sm font-medium">Stage<Input aria-label="stage" className="mt-1" onChange={event => setStage(event.target.value)} value={stage} /></label>
          <label className="text-sm font-medium">Content class<Input aria-label="content class" className="mt-1" onChange={event => setContentClass(event.target.value)} value={contentClass} /></label>
          <p className="text-xs text-muted-foreground">Requested: {stage} · {contentClass}</p>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction disabled={!stage.trim() || !contentClass.trim()} onClick={confirmLocalPreferred}>Confirm Local Preferred</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </CardContent>
  </Card>
}
