'use client'

/**
 * Settings → Local Models page (v0.8.39 Phase 4a — read-only inventory).
 *
 * Lists every GGUF in the configured model directory with metadata
 * (architecture, parameter count, quant, context length, file size).
 * Empty state guides the user to drop GGUFs into the configured path.
 *
 * Future (deferred to v0.8.39b / v0.8.39c):
 *   - "Download" panel with curated HuggingFace recommendations.
 *   - "Set Active" button to hot-swap the chat sidecar's GGUF without
 *     relaunching.
 */

import React from 'react'
import Link from 'next/link'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FolderOpen,
  Cpu,
  Hash,
  HardDrive,
  RefreshCw,
  AlertCircle,
  Sparkles,
  Power,
  Loader2,
} from 'lucide-react'
import { toast } from 'sonner'
import { AppShell } from '@/components/layout/AppShell'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import apiClient from '@/lib/api/client'
import { useTranslation } from '@/lib/hooks/use-translation'
// v0.8.39b — curated HuggingFace recommendations + one-click download
import { DownloadPanel } from './DownloadPanel'

type LocalModel = {
  name: string
  path: string
  architecture: string | null
  context_length: number | null
  quant: string | null
  parameter_count_b: number | null
  file_size_bytes: number
}

type InventoryResponse = {
  model_dir: string
  available: boolean
  models: LocalModel[]
}

function fmtBytes(n: number): string {
  if (!n) return '—'
  const gb = n / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(2)} GB`
  const mb = n / (1024 * 1024)
  return `${mb.toFixed(0)} MB`
}

function fmtNCtx(n: number | null): string {
  if (!n) return '—'
  if (n >= 1024) return `${Math.round(n / 1024)}k`
  return String(n)
}

function fmtParams(n: number | null): string {
  if (!n) return '—'
  return `${n}B`
}

export default function LocalModelsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch } = useQuery<InventoryResponse>({
    queryKey: ['local-models', 'inventory'],
    queryFn: async () => {
      const resp = await apiClient.get<InventoryResponse>('/local-models/inventory')
      return resp.data
    },
    // Inventory is cheap — re-poll on focus so a user who drops a new
    // file in via Finder sees it without manual refresh.
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })

  // v0.8.40b — hot-swap chat GGUF via the launcher control plane.
  // Tracks the path currently being swapped (for button-state UX)
  // so the user sees which card is in-flight even if they click
  // multiple in quick succession.
  const [activatingPath, setActivatingPath] = React.useState<string | null>(null)
  const setActive = useMutation({
    mutationFn: async (path: string) => {
      setActivatingPath(path)
      try {
        const resp = await apiClient.post<{
          ok: boolean; path: string; detail: string
        }>('/local-models/set-active', { path })
        return resp.data
      } finally {
        setActivatingPath(null)
      }
    },
    onSuccess: res => {
      if (res.ok) {
        toast.success(
          t('localModels.setActiveSuccess', {
            defaultValue: 'Active chat model switched: {{detail}}',
            detail: res.detail,
          }),
        )
        // Health badges may flip red briefly while the new sidecar
        // mmaps the GGUF — invalidate so the polling picks up the
        // transition.
        queryClient.invalidateQueries({ queryKey: ['local-models', 'health'] })
      } else {
        toast.error(
          t('localModels.setActiveFailed', {
            defaultValue: 'Could not switch chat model: {{detail}}',
            detail: res.detail,
          }),
        )
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.setActiveFailed', {
          defaultValue: 'Could not switch chat model: {{detail}}',
          detail: msg,
        }),
      )
    },
  })

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="px-6 py-10 sm:px-8 space-y-8 max-w-4xl">
          {/* Header */}
          <header className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
              <Cpu className="h-7 w-7" />
              {t('localModels.title', { defaultValue: 'Local models' })}
            </h1>
            <p className="text-muted-foreground">
              {t('localModels.description', {
                defaultValue:
                  'GGUF files in your configured model directory. The smart router can pick from these when chatting; drop new files in to add them.',
              })}
            </p>
          </header>

          {/* Refresh control */}
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">
              {data && (
                <span className="flex items-center gap-1.5">
                  <FolderOpen className="h-3 w-3" />
                  <code className="bg-muted px-1.5 py-0.5 rounded">{data.model_dir || '—'}</code>
                </span>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => refetch()}
              disabled={isLoading}
              className="gap-1"
            >
              <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
              {t('common.refresh', { defaultValue: 'Refresh' })}
            </Button>
          </div>

          {/* Error state */}
          {isError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.errorTitle', { defaultValue: 'Could not load inventory' })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.errorDesc', {
                  defaultValue: 'The API returned an error. Check the API logs and try again.',
                })}
              </AlertDescription>
            </Alert>
          )}

          {/* Empty / unavailable states */}
          {data && !data.available && (
            <Alert>
              <FolderOpen className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.dirMissingTitle', {
                  defaultValue: 'Model directory not found',
                })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.dirMissingDesc', {
                  defaultValue:
                    'The configured directory does not exist. Create it and drop .gguf files in, then refresh.',
                })}
                {data.model_dir && (
                  <>
                    {' '}
                    <code className="bg-muted px-1 py-0.5 rounded">{data.model_dir}</code>
                  </>
                )}
              </AlertDescription>
            </Alert>
          )}

          {data && data.available && data.models.length === 0 && (
            <Alert>
              <Sparkles className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.emptyTitle', {
                  defaultValue: 'No models installed yet',
                })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.emptyDesc', {
                  defaultValue:
                    'Drop a .gguf file into the directory above, then click Refresh. We recommend Qwen2.5-7B-Instruct-Q4_K_M from HuggingFace as a starting point.',
                })}
                {' '}
                <Link
                  href="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  {t('localModels.emptyLink', { defaultValue: 'Browse on HuggingFace →' })}
                </Link>
              </AlertDescription>
            </Alert>
          )}

          {/* v0.8.39b — Recommendations + downloader.
              Shown whenever the model dir is reachable (even when
              empty — that's actually the most useful place for it:
              brand-new install, nothing installed yet, here are some
              good first picks). Hidden on dir-missing/error states
              since downloads need a real dest dir. */}
          {data && data.available && <DownloadPanel />}

          {/* Inventory list */}
          {data && data.available && data.models.length > 0 && (
            <div className="space-y-3" data-testid="local-models-list">
              {data.models.map(m => (
                <Card key={m.path} data-testid={`local-model-${m.name}`}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="space-y-1">
                        <CardTitle className="text-base font-medium break-all">
                          {m.name}
                        </CardTitle>
                        <CardDescription className="text-xs break-all">
                          {m.path}
                        </CardDescription>
                      </div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {m.quant && (
                          <Badge variant="secondary" className="text-xs">
                            <Hash className="h-3 w-3 mr-1" />
                            {m.quant}
                          </Badge>
                        )}
                        {m.architecture && (
                          <Badge variant="outline" className="text-xs">
                            {m.architecture}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0 space-y-3">
                    <dl className="grid grid-cols-3 gap-3 text-xs">
                      <div>
                        <dt className="text-muted-foreground">
                          {t('localModels.colParams', { defaultValue: 'Parameters' })}
                        </dt>
                        <dd className="font-mono">{fmtParams(m.parameter_count_b)}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">
                          {t('localModels.colContext', { defaultValue: 'Context' })}
                        </dt>
                        <dd className="font-mono">{fmtNCtx(m.context_length)}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground flex items-center gap-1">
                          <HardDrive className="h-3 w-3" />
                          {t('localModels.colSize', { defaultValue: 'Size' })}
                        </dt>
                        <dd className="font-mono">{fmtBytes(m.file_size_bytes)}</dd>
                      </div>
                    </dl>
                    {/* v0.8.40b — Set Active button hot-swaps the chat
                        sidecar's GGUF without quitting the app. Only
                        meaningful for chat-shaped GGUFs (filename has
                        no 'embed' marker); we render the button
                        unconditionally here and let the launcher's
                        own validation reject embedding GGUFs with a
                        clear message via the 400 path. */}
                    <div className="flex justify-end">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 h-7 text-xs"
                        disabled={
                          setActive.isPending || activatingPath === m.path
                        }
                        onClick={() => setActive.mutate(m.path)}
                        data-testid={`set-active-${m.name}`}
                      >
                        {activatingPath === m.path ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Power className="h-3 w-3" />
                        )}
                        {activatingPath === m.path
                          ? t('localModels.activating', {
                              defaultValue: 'Switching…',
                            })
                          : t('localModels.setActive', {
                              defaultValue: 'Set as active chat model',
                            })}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
