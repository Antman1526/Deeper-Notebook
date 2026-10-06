'use client'

import { BrainCircuit, Cpu, Zap } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

type ModelRuntime = 'gguf' | 'mlx' | string | null | undefined

function runtimeLabel(runtime: ModelRuntime, t: (key: string) => string): string {
  if (runtime === 'gguf') return 'GGUF'
  if (runtime === 'mlx') return 'MLX'
  if (runtime === 'transformers') return 'Transformers'
  return t('workspace.modelFleetBadge.runtimeLocal')
}

function runtimeClassName(runtime: ModelRuntime): string {
  if (runtime === 'mlx') {
    return 'border-[var(--dn-model-mlx)] text-[var(--dn-model-mlx)]'
  }
  if (runtime === 'gguf') {
    return 'border-[var(--dn-model-gguf)] text-[var(--dn-model-gguf)]'
  }
  if (runtime === 'transformers') {
    return 'border-[var(--dn-info)] text-[var(--dn-info)]'
  }
  return 'border-[var(--dn-info)] text-[var(--dn-info)]'
}

export function ModelFleetBadge({ runtime }: { runtime: ModelRuntime }) {
  const { t } = useTranslation()
  const label = runtimeLabel(runtime, t)
  const Icon = runtime === 'mlx' ? Zap : runtime === 'transformers' ? BrainCircuit : Cpu

  return (
    <Badge
      variant="outline"
      aria-label={t('workspace.modelFleetBadge.ariaLabel', { runtime: label })}
      className={cn('text-xs', runtimeClassName(runtime))}
    >
      <Icon className="mr-1 h-3 w-3" aria-hidden="true" />
      {label}
    </Badge>
  )
}
