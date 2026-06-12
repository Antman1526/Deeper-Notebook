'use client'

/**
 * SidecarLogPopover.tsx — v0.8.38 Phase 3
 *
 * Popover surface that fetches `/healthz/sidecars/{kind}/log` and renders:
 *   - A user-friendly hint at the top (e.g. "Model file not found")
 *     produced by `classify_sidecar_error` on the backend.
 *   - The raw stderr tail (last ~50 lines) in a monospace block.
 *   - A graceful "no log available" state when the backend reports
 *     `available: false` (API running outside the launcher, sidecar
 *     never spawned, etc).
 *
 * Used by `<LocalModelHealthBadges>` — clicking a red (unhealthy) badge
 * opens this popover so the user can see WHY a sidecar is down without
 * having to enable debug_mode and hunt log files.
 *
 * Restart action (POST /healthz/sidecars/{kind}/restart) is deferred —
 * the launcher and API are separate processes with no IPC channel,
 * implementing restart requires a bidirectional control plane. For
 * now users see the cause + "Restart the app" as the action.
 */

import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, FileText, RotateCw, Loader2 } from 'lucide-react'
import apiClient from '@/lib/api/client'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { toast } from 'sonner'

export type SidecarKind = 'chat' | 'embed' | 'whisper' | 'piper' | 'memory'

type SidecarLogResponse = {
  kind: string
  log: string
  hint: string | null
  available: boolean
}

export interface SidecarLogPopoverProps {
  /** The kind passed to /healthz/sidecars/{kind}/log. Must match the
   * backend's _KIND_TO_SUPERVISOR allowlist. */
  kind: SidecarKind
  /** The trigger element — typically the colored status dot. Receives
   * onClick + cursor-pointer styling via Popover.Trigger asChild. */
  children: React.ReactNode
}

type RestartResponse = {
  kind: string
  ok: boolean
  detail: string
}

export function SidecarLogPopover({ kind, children }: SidecarLogPopoverProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  // Don't auto-fetch — only when the popover opens. Saves bandwidth
  // for badges that never get clicked (the common case).
  const [open, setOpen] = React.useState(false)

  const { data, isLoading, isError } = useQuery<SidecarLogResponse>({
    queryKey: ['healthz', 'sidecars', kind, 'log'],
    queryFn: async () => {
      const resp = await apiClient.get<SidecarLogResponse>(
        `/healthz/sidecars/${kind}/log`,
      )
      return resp.data
    },
    enabled: open,
    refetchOnWindowFocus: false,
    // Short stale time — if the user reopens within 5s, reuse cache;
    // anything longer should pull fresh (sidecar may have died meanwhile).
    staleTime: 5_000,
  })

  // v0.8.40 — restart proxies to the launcher's control plane.
  // On success, invalidate the log query (the new sidecar will
  // produce fresh stderr) and the global health-badges query so the
  // dot can flip back to green.
  const restart = useMutation({
    mutationFn: async () => {
      const resp = await apiClient.post<RestartResponse>(
        `/healthz/sidecars/${kind}/restart`,
      )
      return resp.data
    },
    onSuccess: data => {
      if (data.ok) {
        toast.success(
          t('models.sidecarLog.restartSuccess', {
            defaultValue: 'Sidecar restarted: {{detail}}',
            detail: data.detail,
          }),
        )
        queryClient.invalidateQueries({
          queryKey: ['healthz', 'sidecars', kind, 'log'],
        })
        queryClient.invalidateQueries({ queryKey: ['local-models', 'health'] })
      } else {
        toast.error(
          t('models.sidecarLog.restartFailedDetail', {
            defaultValue: 'Restart failed: {{detail}}',
            detail: data.detail,
          }),
        )
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('models.sidecarLog.restartFailedDetail', {
          defaultValue: 'Restart failed: {{detail}}',
          detail: msg,
        }),
      )
    },
  })

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        side="right"
        align="start"
        className="w-96 max-w-[90vw] p-3 space-y-2"
        data-testid={`sidecar-log-popover-${kind}`}
      >
        <div className="flex items-center gap-1.5 text-xs font-medium">
          <FileText className="h-3 w-3" />
          {t('models.sidecarLog.title', {
            defaultValue: 'Sidecar log ({{kind}})',
            kind,
          })}
        </div>

        {isLoading && (
          <p className="text-xs text-muted-foreground">
            {t('common.loading', { defaultValue: 'Loading…' })}
          </p>
        )}

        {isError && (
          <p className="text-xs text-destructive">
            {t('models.sidecarLog.fetchError', {
              defaultValue: 'Could not load sidecar log',
            })}
          </p>
        )}

        {data && !data.available && (
          <p className="text-xs text-muted-foreground">
            {t('models.sidecarLog.unavailable', {
              defaultValue:
                'No log captured for this sidecar. Try restarting the app — the launcher writes a per-sidecar tail file as it runs.',
            })}
          </p>
        )}

        {data && data.available && (
          <>
            {data.hint && (
              <div className="flex items-start gap-1.5 text-xs rounded bg-amber-50 dark:bg-amber-950/20 border border-amber-300 dark:border-amber-700 p-2">
                <AlertCircle className="h-3 w-3 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                <span className="text-amber-900 dark:text-amber-100">
                  {data.hint}
                </span>
              </div>
            )}
            {data.log ? (
              <pre className="text-[10px] font-mono whitespace-pre-wrap break-all max-h-64 overflow-y-auto rounded bg-muted p-2">
                {data.log}
              </pre>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t('models.sidecarLog.empty', {
                  defaultValue:
                    'Sidecar started cleanly — no stderr captured.',
                })}
              </p>
            )}
            {/* v0.8.40 — in-place restart via the launcher control
                plane. Disabled while the mutation is in flight; toast
                surfaces success/error. */}
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] text-muted-foreground flex-1">
                {t('models.sidecarLog.restartHintInline', {
                  defaultValue:
                    'Restart this sidecar without quitting the app.',
                })}
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => restart.mutate()}
                disabled={restart.isPending}
                className="gap-1 h-7 text-xs"
                data-testid={`sidecar-restart-${kind}`}
              >
                {restart.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <RotateCw className="h-3 w-3" />
                )}
                {restart.isPending
                  ? t('models.sidecarLog.restarting', {
                      defaultValue: 'Restarting…',
                    })
                  : t('models.sidecarLog.restart', { defaultValue: 'Restart' })}
              </Button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

/**
 * Heuristic mapping from a credential `name` (as returned by the
 * `/api/local-models/health` probe — e.g. "Local GGUF (llama.cpp)",
 * "Local Embeddings (llama.cpp)") to the canonical sidecar kind the
 * `/healthz/sidecars/{kind}/log` endpoint expects.
 *
 * Returns null when the name doesn't look like one of our bundled
 * sidecars — caller should skip rendering the popover.
 */
export function sidecarKindFromName(name: string): SidecarKind | null {
  const n = name.toLowerCase()
  if (n.includes('embed')) return 'embed'
  if (n.includes('whisper') || n.includes('stt')) return 'whisper'
  if (n.includes('piper') || n.includes('tts')) return 'piper'
  if (n.includes('memory')) return 'memory'
  if (n.includes('llama') || n.includes('gguf') || n.includes('chat')) return 'chat'
  return null
}

export default SidecarLogPopover
