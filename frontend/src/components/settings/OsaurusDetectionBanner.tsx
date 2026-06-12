'use client'

/**
 * OsaurusDetectionBanner.tsx — v0.8.36 Phase 1
 *
 * Banner card shown on the Settings → API Keys page when:
 *   - The user has NO credential named "Osaurus (local MLX)" yet, AND
 *   - Our backend's POST /credentials/detect-osaurus probe reports
 *     `running: true` (i.e., Osaurus is reachable on localhost:1337
 *     or the OPEN_NOTEBOOK_OSAURUS_PORT override).
 *
 * One-click "Connect" calls the same endpoint with side-effects
 * enabled, which auto-registers the credential + model rows. After
 * success, we invalidate the credentials and models queries so the
 * rest of the page re-renders with the new entries — same pattern
 * as `useMigrateFromEnv` in `use-credentials.ts`.
 *
 * If Osaurus isn't running, the banner renders nothing — users who
 * don't use Osaurus see no clutter. We intentionally do NOT poll;
 * users who install Osaurus later can hit a manual "Detect Osaurus"
 * action (deferred to a follow-up — for now, page reload triggers
 * a fresh probe).
 */

import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, ExternalLink, CheckCircle2 } from 'lucide-react'
import apiClient from '@/lib/api/client'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { toast } from 'sonner'
import { CREDENTIAL_QUERY_KEYS } from '@/lib/hooks/use-credentials'
import { MODEL_QUERY_KEYS } from '@/lib/hooks/use-models'
import type { Credential } from '@/lib/api/credentials'

type DetectResponse = {
  running: boolean
  port: number
  models_registered: number
  credential_id: string | null
  detail: string
}

const DETECT_QUERY_KEY = ['credentials', 'detect-osaurus'] as const

export interface OsaurusDetectionBannerProps {
  credentials: Credential[] | undefined
}

export function OsaurusDetectionBanner({ credentials }: OsaurusDetectionBannerProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Hide entirely if the Osaurus credential already exists. Name match
  // mirrors what `register_osaurus_models` writes — keep them in sync.
  const alreadyConnected = !!credentials?.some(
    c => c.name?.toLowerCase() === 'osaurus (local mlx)',
  )

  // Probe the backend once per mount. The probe itself short-circuits
  // (single httpx.ConnectError, ~2-5s worst case) when Osaurus isn't
  // running, so this is cheap even on cold misses.
  const { data, isLoading } = useQuery<DetectResponse>({
    queryKey: DETECT_QUERY_KEY,
    queryFn: async () => {
      // We POST with a flag-less body — the backend's idempotent
      // detect endpoint runs the probe + register flow. If we hide
      // the banner anyway when already-connected, the auto-trigger
      // is safe.
      const resp = await apiClient.post<DetectResponse>(
        '/credentials/detect-osaurus',
      )
      return resp.data
    },
    enabled: !alreadyConnected,
    // No retry — Osaurus not running is a normal state, not a failure.
    retry: false,
    // Don't refetch on focus — this is a one-shot probe.
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000,
  })

  const reconnect = useMutation({
    mutationFn: async () => {
      const resp = await apiClient.post<DetectResponse>(
        '/credentials/detect-osaurus',
      )
      return resp.data
    },
    onSuccess: data => {
      queryClient.invalidateQueries({ queryKey: CREDENTIAL_QUERY_KEYS.all })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      toast.success(
        t('apiKeys.osaurus.connectSuccess', {
          defaultValue: 'Connected to Osaurus ({{count}} models registered)',
          count: data.models_registered,
        }),
      )
    },
    onError: () => {
      toast.error(
        t('apiKeys.osaurus.connectError', {
          defaultValue: 'Could not connect to Osaurus — see API logs',
        }),
      )
    },
  })

  // Don't render anything until we know whether Osaurus is reachable.
  // Suppresses banner flicker on slow probe.
  if (alreadyConnected) return null
  if (isLoading) return null
  if (!data || !data.running) return null

  return (
    <Alert className="border-violet-500/50 bg-violet-50 dark:bg-violet-950/20">
      <Sparkles className="h-4 w-4 text-violet-600 dark:text-violet-400" />
      <AlertTitle className="text-violet-900 dark:text-violet-100">
        {t('apiKeys.osaurus.detectedTitle', {
          defaultValue: 'Osaurus detected on port {{port}}',
          port: data.port,
        })}
      </AlertTitle>
      <AlertDescription className="text-violet-800 dark:text-violet-200 space-y-2">
        <p>
          {t('apiKeys.osaurus.detectedDescription', {
            defaultValue:
              'Osaurus (MLX-accelerated local AI for Apple Silicon) is running on your machine. Connect it as a local provider — typically 2-4× faster than llama.cpp on M-series chips.',
          })}
        </p>
        <div className="flex items-center gap-2 pt-1">
          <Button
            size="sm"
            onClick={() => reconnect.mutate()}
            disabled={reconnect.isPending}
            className="gap-1"
          >
            <CheckCircle2 className="h-3 w-3" />
            {reconnect.isPending
              ? t('apiKeys.osaurus.connecting', { defaultValue: 'Connecting…' })
              : t('apiKeys.osaurus.connectButton', { defaultValue: 'Connect Osaurus' })}
          </Button>
          <Button
            size="sm"
            variant="outline"
            asChild
            className="gap-1"
          >
            <a
              href="https://github.com/osaurus-ai/osaurus"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink className="h-3 w-3" />
              {t('apiKeys.osaurus.learnMore', { defaultValue: 'Learn more' })}
            </a>
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  )
}

export default OsaurusDetectionBanner
