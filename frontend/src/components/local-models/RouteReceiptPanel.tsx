import { ClipboardCheck, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { RouteReceipt } from '@/lib/api/local-models'
import { MODEL_ROLE_KEYS, enumLabel } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'

const roleLabel = (role: string, t: (key: string) => string) => enumLabel(t, MODEL_ROLE_KEYS, role, role.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()))
const ageLabel = (seconds: number, t: (key: string, options?: Record<string, unknown>) => string) => seconds < 3600
  ? t('settings.routeReceiptPanel.ageMinutes', { count: Math.floor(seconds / 60) })
  : t('settings.routeReceiptPanel.ageDays', { count: Math.floor(seconds / 86400) })

export function RouteReceiptPanel({ receipts, isLoading, isError }: { receipts: RouteReceipt[]; isLoading: boolean; isError: boolean }) {
  const { t } = useTranslation()
  return <Card><CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><ClipboardCheck className="h-4 w-4" />{t('settings.routeReceiptPanel.title')}</CardTitle><CardDescription>{t('settings.routeReceiptPanel.description')}</CardDescription></CardHeader><CardContent>{isLoading ? <p className="text-sm text-muted-foreground">{t('settings.routeReceiptPanel.loading')}</p> : isError ? <p className="text-sm text-muted-foreground">{t('settings.routeReceiptPanel.notExposed')}</p> : receipts.length === 0 ? <p className="text-sm text-muted-foreground">{t('settings.routeReceiptPanel.empty')}</p> : <div className="space-y-2">{receipts.slice(0, 8).map((receipt, index) => <div className="grid gap-2 rounded-md border px-3 py-2 text-xs sm:grid-cols-[1fr_auto]" key={`${receipt.selected_model_id}-${receipt.role}-${index}`}><div><p className="font-medium">{roleLabel(receipt.role, t)} <Badge className="ml-1" variant="outline">{receipt.outcome}</Badge></p><p className="mt-1 font-mono">{receipt.selected_model_id}</p><p className="mt-1 text-muted-foreground">{receipt.reason}</p></div><div className="text-left sm:text-right"><p className="text-muted-foreground">{t('settings.routeReceiptPanel.measurement')}</p><p>{ageLabel(receipt.benchmark_age_seconds, t)}</p>{receipt.fallback_model_id && <><p className="mt-1 text-muted-foreground">{t('settings.routeReceiptPanel.oneFallback')}</p><p className="font-mono">{receipt.fallback_model_id}</p></>}</div></div>)}</div>}<div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5" />{t('settings.routeReceiptPanel.forcedOffline')}</div></CardContent></Card>
}
