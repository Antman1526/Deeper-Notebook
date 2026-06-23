'use client'

/**
 * RecommendationsPanel.tsx — v0.8.41
 *
 * Curated MCP server recommendations (SearXNG, Crawl4AI, Playwright)
 * with one-click "Connect" — pre-fills the create-server form and
 * POSTs to `/api/mcp` (the existing v0.8.0 endpoint).
 *
 * UX mirrors the v0.8.39b GGUF DownloadPanel:
 *   - Card-per-recommendation grid above the existing server list.
 *   - Tag badges (search / scraping / browser / recommended /
 *     "replaces $X").
 *   - "Install" link → upstream docs (Docker/npm — the user has to
 *     bring the server up themselves; we can't install it for them
 *     the way we can for GGUFs).
 *   - "Connect" button → calls POST /api/mcp with the recommendation's
 *     label + default_url. Skips if a server with that name already
 *     exists (toast feedback) — avoids duplicates on re-click.
 */

import React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Server,
  ExternalLink,
  CheckCircle2,
  Plug,
  Loader2,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/lib/api/client'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useCreateMCPServer, useMCPServers } from '@/lib/hooks/use-mcp-servers'
import { toast } from 'sonner'

export type MCPRecommendation = {
  id: string
  label: string
  description: string
  default_url: string
  install_url: string
  tags: string[]
  replaces: string | null
}

type RecommendationsResponse = {
  recommendations: MCPRecommendation[]
}

export function RecommendationsPanel() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data: existingServers } = useMCPServers()
  const create = useCreateMCPServer()

  const { data, isLoading } = useQuery<RecommendationsResponse>({
    queryKey: ['mcp', 'recommendations'],
    queryFn: async () => {
      const resp = await apiClient.get<RecommendationsResponse>(
        '/mcp/recommendations',
      )
      return resp.data
    },
    staleTime: Infinity,
  })

  // Pending state per-card so multiple cards can be clicked without
  // them all showing the spinner.
  const [pendingId, setPendingId] = React.useState<string | null>(null)

  const isAlreadyConnected = (rec: MCPRecommendation): boolean => {
    if (!existingServers) return false
    const norm = (s: string) => s.trim().toLowerCase()
    return existingServers.some(
      s => norm(s.name) === norm(rec.label) || norm(s.url) === norm(rec.default_url),
    )
  }

  const handleConnect = async (rec: MCPRecommendation) => {
    if (isAlreadyConnected(rec)) {
      // Defense — the button is already disabled in this state, but
      // keep the no-op explicit.
      toast.info(
        t('mcp.recommendations.alreadyConnected', {
          defaultValue: '{{label}} is already connected',
          label: rec.label,
        }),
      )
      return
    }
    setPendingId(rec.id)
    try {
      await create.mutateAsync({
        name: rec.label,
        url: rec.default_url,
        enabled: true,
      })
      toast.success(
        t('mcp.recommendations.connectSuccess', {
          defaultValue: 'Connected to {{label}}',
          label: rec.label,
        }),
      )
      // Invalidate the servers query so the row appears in the
      // existing-servers list below without manual refresh. (The
      // mutation hook already invalidates, but explicit here is
      // defensive.)
      queryClient.invalidateQueries({ queryKey: ['mcp', 'servers'] })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('mcp.recommendations.connectError', {
          defaultValue: 'Could not connect: {{detail}}',
          detail: msg,
        }),
      )
    } finally {
      setPendingId(null)
    }
  }

  if (isLoading || !data) return null

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Server className="h-4 w-4" />
          {t('mcp.recommendations.header', {
            defaultValue: 'Recommended MCP servers',
          })}
        </h2>
        <p className="text-xs text-muted-foreground">
          {t('mcp.recommendations.subheader', {
            defaultValue:
              'Curated, locally-runnable servers we have validated work with the chat tool loop. Install via the upstream link, then click Connect.',
          })}
        </p>
      </header>

      <div className="space-y-3" data-testid="mcp-recommendations-list">
        {data.recommendations.map(rec => {
          const connected = isAlreadyConnected(rec)
          const inFlight = pendingId === rec.id
          return (
            <Card key={rec.id} data-testid={`mcp-recommendation-${rec.id}`}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="space-y-1 flex-1 min-w-0">
                    <CardTitle className="text-base font-medium">
                      {rec.label}
                    </CardTitle>
                    <CardDescription className="text-xs">
                      {rec.description}
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-1 flex-wrap">
                    {rec.tags.map(tag => (
                      <Badge
                        key={tag}
                        variant={tag === 'recommended' ? 'default' : 'secondary'}
                        className="text-[10px]"
                      >
                        {tag}
                      </Badge>
                    ))}
                    {rec.replaces && (
                      <Badge variant="outline" className="text-[10px]">
                        {t('mcp.recommendations.replaces', {
                          defaultValue: 'Replaces {{name}}',
                          name: rec.replaces,
                        })}
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-3">
                <p className="text-[10px] text-muted-foreground font-mono break-all">
                  {rec.default_url}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => handleConnect(rec)}
                    disabled={inFlight || connected || create.isPending}
                    className="gap-1.5"
                    data-testid={`mcp-connect-${rec.id}`}
                  >
                    {inFlight ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : connected ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <Plug className="h-3 w-3" />
                    )}
                    {inFlight
                      ? t('mcp.recommendations.connecting', {
                          defaultValue: 'Connecting…',
                        })
                      : connected
                        ? t('mcp.recommendations.connected', {
                            defaultValue: 'Connected',
                          })
                        : t('mcp.recommendations.connect', {
                            defaultValue: 'Connect',
                          })}
                  </Button>
                  <Button size="sm" variant="outline" asChild className="gap-1">
                    <a
                      href={rec.install_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {t('mcp.recommendations.installLink', {
                        defaultValue: 'Install instructions',
                      })}
                    </a>
                  </Button>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </section>
  )
}

export default RecommendationsPanel
