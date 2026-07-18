import { Badge } from '@/components/ui/badge'
import type { CaptureItem } from '@/lib/api/capture'

const stateVariant = (state: CaptureItem['state']) => state === 'failed' ? 'destructive' : state === 'imported' ? 'secondary' : 'outline'

export function CaptureItemRow({ item }: { item: CaptureItem }) {
  return <article className="grid gap-2 border-b py-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"><div className="min-w-0"><p className="truncate text-sm font-medium">{item.filename}</p><p className="truncate text-xs text-muted-foreground">{item.relative_path} · {item.extension || 'unknown type'}{item.byte_size ? ` · ${(item.byte_size / 1024).toFixed(1)} KB` : ''}</p>{item.reason ? <p className="mt-1 text-xs text-destructive">{item.reason}</p> : null}</div><Badge variant={stateVariant(item.state)} className="w-fit">{item.state}</Badge></article>
}
