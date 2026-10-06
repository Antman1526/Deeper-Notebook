'use client'

import Link from 'next/link'
import { Cpu } from 'lucide-react'

import { useLocalModelsHealth } from '@/lib/hooks/use-local-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

/**
 * v0.8.130 — model health in the command bar while the rail (which lists it) is a
 * sheet, below 1024px. Shown only when something needs attention; it links to the
 * page that explains and fixes it.
 */
export function ModelHealthIndicator() {
  const { data } = useLocalModelsHealth()
  const { t } = useTranslation()
  if (!data || data.overall === 'healthy') return null

  const down = data.overall === 'down'
  const label = down ? t('navigation.modelHealthDown') : t('navigation.modelHealthDegraded')
  return (
    <Link href="/settings/local-models" className="dn-command-health" aria-label={label} title={label}>
      <Cpu className="h-4 w-4" aria-hidden="true" />
      <span className={cn('dn-command-health-dot', down ? 'bg-destructive' : 'bg-warning')} aria-hidden="true" />
    </Link>
  )
}
