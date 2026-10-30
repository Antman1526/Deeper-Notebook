'use client'

import { useState } from 'react'

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { LocalModelSettings } from '@/lib/api/local-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import { RichText } from '@/components/common/RichText'

type Props = {
  policy: LocalModelSettings['execution_policy']
  computeProfile: LocalModelSettings['compute_profile']
  memoryLimitBytes: number | null
  pendingCloudRoute?: { stage: string; contentClass: string } | null
  onConfirmCloudRoute?: (route: { stage: string; contentClass: string }) => void
  isSaving?: boolean
  onSave: (next: Pick<LocalModelSettings, 'execution_policy' | 'compute_profile' | 'local_model_memory_limit_bytes'>) => void
}

const labelKeys = {
  strict_local: 'settings.localExecutionPolicyPanel.strictLocal',
  local_preferred: 'settings.localExecutionPolicyPanel.useLocalPreferred',
  custom: 'settings.localExecutionPolicyPanel.custom',
} as const

export function LocalExecutionPolicyPanel({ policy, computeProfile, memoryLimitBytes, pendingCloudRoute = null, onConfirmCloudRoute, isSaving, onSave }: Props) {
  const { t } = useTranslation()
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
    <CardHeader className="pb-3"><CardTitle className="text-base">{t('settings.localExecutionPolicyPanel.title')}</CardTitle><CardDescription>{t('settings.localExecutionPolicyPanel.description')}</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label={t('settings.localExecutionPolicyPanel.executionPolicyAria')}>
        {(Object.keys(labelKeys) as LocalModelSettings['execution_policy'][]).map(value => <Button key={value} type="button" variant={nextPolicy === value ? 'default' : 'outline'} onClick={() => choosePolicy(value)}>
          {t(labelKeys[value])}
        </Button>)}
      </div>
      {strictBlocksCloud && <p role="alert" className="text-sm text-destructive">{t('settings.localExecutionPolicyPanel.strictBlocksCloud')}</p>}
      {canReviewCloudFallback && <div className="rounded-md border p-3 text-sm"><p><RichText text={t('settings.localExecutionPolicyPanel.cloudFallbackProposed')} components={{ stage: () => <strong>{pendingCloudRoute!.stage}</strong>, content: () => <strong>{pendingCloudRoute!.contentClass}</strong> }} /></p><Button className="mt-2" onClick={() => setConfirmOpen(true)} size="sm" type="button" variant="outline">{t('settings.localExecutionPolicyPanel.reviewPendingCloudFallback')}</Button></div>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm font-medium">{t('settings.localExecutionPolicyPanel.computeProfile')}<select aria-label={t('settings.localExecutionPolicyPanel.computeProfile')} className="mt-1 w-full rounded-md border bg-background p-2" value={nextProfile} onChange={event => setNextProfile(event.target.value as LocalModelSettings['compute_profile'])}><option value="efficient">{t('settings.localExecutionPolicyPanel.profileEfficient')}</option><option value="balanced">{t('settings.localExecutionPolicyPanel.profileBalanced')}</option><option value="maximum_quality">{t('settings.localExecutionPolicyPanel.profileMaximumQuality')}</option></select></label>
        <label className="text-sm font-medium">{t('settings.localExecutionPolicyPanel.memoryLimit')}<Input aria-label={t('settings.localExecutionPolicyPanel.memoryLimitAria')} className="mt-1" inputMode="numeric" min="0" onChange={event => setNextLimit(event.target.value)} value={nextLimit} /></label>
      </div>
      <Button className="h-auto min-h-11 w-full whitespace-normal sm:w-auto" type="button" disabled={Boolean(isSaving) || !validLimit} onClick={() => onSave({ execution_policy: nextPolicy, compute_profile: nextProfile, local_model_memory_limit_bytes: limit })}>{t('settings.localExecutionPolicyPanel.save')}</Button>
      {canReviewCloudFallback && <AlertDialog open={confirmOpen} onOpenChange={handleCloudDialogOpenChange}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>{t('settings.localExecutionPolicyPanel.confirmTitle')}</AlertDialogTitle><AlertDialogDescription>{t('settings.localExecutionPolicyPanel.confirmDescription')}</AlertDialogDescription></AlertDialogHeader>
          <label className="text-sm font-medium">{t('settings.localExecutionPolicyPanel.stage')}<Input aria-label={t('settings.localExecutionPolicyPanel.stageAria')} className="mt-1" onChange={event => setStage(event.target.value)} value={stage} /></label>
          <label className="text-sm font-medium">{t('settings.localExecutionPolicyPanel.contentClass')}<Input aria-label={t('settings.localExecutionPolicyPanel.contentClassAria')} className="mt-1" onChange={event => setContentClass(event.target.value)} value={contentClass} /></label>
          <p className="text-xs text-muted-foreground">{t('settings.localExecutionPolicyPanel.proposed')} {pendingCloudRoute!.stage} · {pendingCloudRoute!.contentClass}</p>
          <AlertDialogFooter><AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel><AlertDialogAction disabled={stage !== pendingCloudRoute!.stage || contentClass !== pendingCloudRoute!.contentClass} onClick={confirmCloudContinuation}>{t('settings.localExecutionPolicyPanel.confirmAction')}</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>}
    </CardContent>
  </Card>
}
