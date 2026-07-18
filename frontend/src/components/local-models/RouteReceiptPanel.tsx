import { ClipboardCheck, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { RouteReceipt } from '@/lib/api/local-models'

const roleLabel = (role: string) => role.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase())
const ageLabel = (seconds: number) => seconds < 3600 ? `${Math.floor(seconds / 60)}m old` : `${Math.floor(seconds / 86400)}d old`

export function RouteReceiptPanel({ receipts, isLoading, isError }: { receipts: RouteReceipt[]; isLoading: boolean; isError: boolean }) {
  return <Card><CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><ClipboardCheck className="h-4 w-4" />Routing receipts</CardTitle><CardDescription>Private routing evidence only: model IDs, role, measurement age, and outcome. Prompts and source text are never stored here.</CardDescription></CardHeader><CardContent>{isLoading ? <p className="text-sm text-muted-foreground">Loading recent routes...</p> : isError ? <p className="text-sm text-muted-foreground">Route receipts are not exposed by this runtime yet.</p> : receipts.length === 0 ? <p className="text-sm text-muted-foreground">No measured route has been used in this session.</p> : <div className="space-y-2">{receipts.slice(0, 8).map((receipt, index) => <div className="grid gap-2 rounded-md border px-3 py-2 text-xs sm:grid-cols-[1fr_auto]" key={`${receipt.selected_model_id}-${receipt.role}-${index}`}><div><p className="font-medium">{roleLabel(receipt.role)} <Badge className="ml-1" variant="outline">{receipt.outcome}</Badge></p><p className="mt-1 font-mono">{receipt.selected_model_id}</p><p className="mt-1 text-muted-foreground">{receipt.reason}</p></div><div className="text-left sm:text-right"><p className="text-muted-foreground">Measurement</p><p>{ageLabel(receipt.benchmark_age_seconds)}</p>{receipt.fallback_model_id && <><p className="mt-1 text-muted-foreground">One fallback</p><p className="font-mono">{receipt.fallback_model_id}</p></>}</div></div>)}</div>}<div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5" />Forced-offline routing excludes cloud providers.</div></CardContent></Card>
}
