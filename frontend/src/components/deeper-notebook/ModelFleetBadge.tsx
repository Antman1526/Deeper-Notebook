import { BrainCircuit, Cpu, Zap } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type ModelRuntime = 'gguf' | 'mlx' | string | null | undefined

function runtimeLabel(runtime: ModelRuntime): string {
  if (runtime === 'gguf') return 'GGUF'
  if (runtime === 'mlx') return 'MLX'
  if (runtime === 'transformers') return 'Transformers'
  return 'Local'
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
  const label = runtimeLabel(runtime)
  const Icon = runtime === 'mlx' ? Zap : runtime === 'transformers' ? BrainCircuit : Cpu

  return (
    <Badge
      variant="outline"
      aria-label={`${label} local model runtime`}
      className={cn('text-xs', runtimeClassName(runtime))}
    >
      <Icon className="mr-1 h-3 w-3" aria-hidden="true" />
      {label}
    </Badge>
  )
}
