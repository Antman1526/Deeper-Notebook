'use client'

// v0.8.0 Phase 2 Task 10 — Settings page for MCP server management.
// Provides list / add / test / delete for MCP servers whose CRUD
// endpoints were added in Task 9 (api/routers/mcp.py).
//
// Design choices vs. spec:
//   - All strings i18n'd via useTranslation / settings.mcp.* keys.
//   - Delete button per row, confirmed via window.confirm (MVP; matches
//     other settings pages' lightweight approach — no Radix Dialog needed).
//   - Test result surfaced via sonner toast (handled in the mutation hook,
//     so this page stays clean).
//   - Inline URL validation: http(s):// prefix check + trim before submit.

import { useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  useMCPServers,
  useCreateMCPServer,
  useTestMCPServer,
  useDeleteMCPServer,
} from '@/lib/hooks/use-mcp-servers'

// Inline URL validity check — no extra dependency needed.
function isValidUrl(url: string): boolean {
  const trimmed = url.trim()
  return trimmed.startsWith('http://') || trimmed.startsWith('https://')
}

export default function MCPServersPage() {
  const { t } = useTranslation()

  const { data: servers = [], isLoading } = useMCPServers()
  const create = useCreateMCPServer()
  const test = useTestMCPServer()
  const del = useDeleteMCPServer()

  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  const canAdd =
    name.trim().length > 0 && isValidUrl(url) && !create.isPending

  const handleAdd = () => {
    if (!canAdd) return
    create.mutate(
      { name: name.trim(), url: url.trim(), enabled: true },
      {
        onSuccess: () => {
          setName('')
          setUrl('')
        },
      },
    )
  }

  const handleDelete = (id: string, serverName: string) => {
    const confirmed = window.confirm(
      t('settings.mcp.deleteConfirm').replace('{name}', serverName),
    )
    if (!confirmed) return
    del.mutate(id)
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="px-6 py-10 sm:px-8">
          <div className="mx-auto max-w-3xl space-y-10">
            <header className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight">
                {t('settings.mcp.title')}
              </h1>
              <p className="text-sm text-muted-foreground">
                {t('settings.mcp.description')}
              </p>
            </header>

            {/* Add-server form */}
            <section className="space-y-4">
              <h2 className="text-lg font-medium">{t('settings.mcp.addTitle')}</h2>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Input
                  placeholder={t('settings.mcp.namePlaceholder')}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="sm:w-48"
                  aria-label={t('settings.mcp.namePlaceholder')}
                />
                <Input
                  placeholder={t('settings.mcp.urlPlaceholder')}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="flex-1"
                  aria-label={t('settings.mcp.urlPlaceholder')}
                  type="url"
                />
                <Button
                  onClick={handleAdd}
                  disabled={!canAdd}
                >
                  {create.isPending
                    ? t('settings.mcp.adding')
                    : t('settings.mcp.addButton')}
                </Button>
              </div>
            </section>

            {/* Server list */}
            <section className="space-y-3">
              <h2 className="text-lg font-medium">{t('settings.mcp.listTitle')}</h2>

              {isLoading && (
                <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
              )}

              {!isLoading && servers.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  {t('settings.mcp.empty')}
                </p>
              )}

              {servers.length > 0 && (
                <ul className="divide-y divide-border rounded-md border">
                  {servers.map((server) => (
                    <li
                      key={server.id}
                      className="flex items-center justify-between gap-4 px-4 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-sm">{server.name}</p>
                        <p className="truncate text-xs text-muted-foreground">{server.url}</p>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => test.mutate(server.id)}
                          disabled={test.isPending}
                          aria-label={t('settings.mcp.testButton')}
                        >
                          {t('settings.mcp.testButton')}
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleDelete(server.id, server.name)}
                          disabled={del.isPending}
                          aria-label={t('settings.mcp.deleteButton')}
                        >
                          {t('settings.mcp.deleteButton')}
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
