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
  pendingCloudRoute?: { stage: string; contentClass: string } | null
  onConfirmCloudRoute?: (route: { stage: string; contentClass: string }) => void
  isSaving?: boolean
  onSave: (next: Pick<LocalModelSettings, 'execution_policy' | 'compute_profile' | 'local_model_memory_limit_bytes'>) => void
}

const labels = { strict_local: 'Strict Local', local_preferred: 'Local Preferred', custom: 'Custom' } as const

export function LocalExecutionPolicyPanel({ policy, computeProfile, memoryLimitBytes, pendingCloudRoute = null, onConfirmCloudRoute, isSaving, onSave }: Props) {
  const [nextPolicy, setNextPolicy] = useState(policy)
  const [nextProfile, setNextProfile] = useState(computeProfile)
  const [nextLimit, setNextLimit] = useState(memoryLimitBytes?.toString() ?? '0')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [stage, setStage] = useState('')
  const [contentClass, setContentClass] = useState('')
  const strictBlocksCloud = policy === 'strict_local' && Boolean(pendingCloudRoute)
  const canReviewCloudFallback = policy === 'local_preferred' && Boolean(pendingCloudRoute && onConfirmCloudRoute)
  const limit = Number(nextLimit)
  const validLimit = Number.isSafeInteger(limit) && limit >= 0

  const choosePolicy = (value: LocalModelSettings['execution_policy']) => {
    setNextPolicy(value)
  }
  const confirmCloudContinuation = () => {
    if (!pendingCloudRoute || stage !== pendingCloudRoute.stage || contentClass !== pendingCloudRoute.contentClass) return
    onConfirmCloudRoute?.(pendingCloudRoute)
    setConfirmOpen(false)
    setStage('')
    setContentClass('')
  }
  const handleCloudDialogOpenChange = (open: boolean) => {
    setConfirmOpen(open)
    if (!open) {
      setStage('')
      setContentClass('')
    }
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
      {canReviewCloudFallback && <div className="rounded-md border p-3 text-sm"><p>Cloud fallback proposed for <strong>{pendingCloudRoute!.stage}</strong> · <strong>{pendingCloudRoute!.contentClass}</strong>.</p><Button className="mt-2" onClick={() => setConfirmOpen(true)} size="sm" type="button" variant="outline">Review pending cloud fallback</Button></div>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium">Compute profile<select aria-label="Compute profile" className="mt-1 w-full rounded-md border bg-background p-2" value={nextProfile} onChange={event => setNextProfile(event.target.value as LocalModelSettings['compute_profile'])}><option value="efficient">Efficient</option><option value="balanced">Balanced</option><option value="maximum_quality">Maximum quality</option></select></label>
        <label className="text-sm font-medium">Memory limit (bytes)<Input aria-label="Memory limit bytes" className="mt-1" inputMode="numeric" min="0" onChange={event => setNextLimit(event.target.value)} value={nextLimit} /></label>
      </div>
      <Button className="w-full sm:w-auto" type="button" disabled={Boolean(isSaving) || !validLimit} onClick={() => onSave({ execution_policy: nextPolicy, compute_profile: nextProfile, local_model_memory_limit_bytes: limit })}>Save local execution policy</Button>
      {canReviewCloudFallback && <AlertDialog open={confirmOpen} onOpenChange={handleCloudDialogOpenChange}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Confirm pending Local Preferred cloud route</AlertDialogTitle><AlertDialogDescription>Type the exact proposed stage and content class to record an approved continuation. This does not execute a task or call a cloud provider.</AlertDialogDescription></AlertDialogHeader>
          <label className="text-sm font-medium">Stage<Input aria-label="stage" className="mt-1" onChange={event => setStage(event.target.value)} value={stage} /></label>
          <label className="text-sm font-medium">Content class<Input aria-label="content class" className="mt-1" onChange={event => setContentClass(event.target.value)} value={contentClass} /></label>
          <p className="text-xs text-muted-foreground">Proposed: {pendingCloudRoute!.stage} · {pendingCloudRoute!.contentClass}</p>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction disabled={stage !== pendingCloudRoute!.stage || contentClass !== pendingCloudRoute!.contentClass} onClick={confirmCloudContinuation}>Confirm cloud continuation</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>}
    </CardContent>
  </Card>
}
