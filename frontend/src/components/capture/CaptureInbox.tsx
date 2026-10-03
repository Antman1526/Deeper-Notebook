'use client'

import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Folder, FolderPlus, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCaptureActions, useCaptureItems, useCaptureRoots } from '@/lib/hooks/use-capture'
import { isVisualSystemV2Enabled } from '@/lib/features'
import { useSourceVisualsEnabled } from '@/lib/features-client'
import { useTranslation } from '@/lib/hooks/use-translation'
import { CaptureItemRow } from './CaptureItemRow'

export function CaptureInbox() {
  const { t } = useTranslation()
  const roots = useCaptureRoots()
  const items = useCaptureItems()
  const actions = useCaptureActions()
  const sourceVisualsEnabled = useSourceVisualsEnabled()
  const showVisualCover = isVisualSystemV2Enabled() && sourceVisualsEnabled
  const [path, setPath] = useState('')

  const addRoot = async () => {
    if (!path.trim()) return
    await actions.addRoot.mutateAsync(path.trim())
    setPath('')
  }

  const scan = () => void actions.scan.mutateAsync(undefined)

  return (
    <div className="space-y-6 max-w-4xl">
      {/* v0.8.130 — named transitions, no press-scale (UI audit Phase 1) */}
      <div className="group relative rounded-xl">
        <div className="rounded-xl bg-card p-5 space-y-4 border">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-foreground">{t('capture.captureInbox.approvedFolders')}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t('capture.captureInbox.approvedFoldersDesc')}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={scan}
              disabled={actions.scan.isPending}
              className="rounded-md duration-150 shadow-xs"
            >
              <RefreshCw
                className={`mr-2 h-4 w-4 ${actions.scan.isPending ? 'animate-spin' : ''}`}
              />
              {t('capture.captureInbox.scanNow')}
            </Button>
          </div>

          {roots.data && roots.data.length > 0 ? (
            <ul className="space-y-1.5 rounded-xl border border-border/50 bg-muted/30 p-3 text-sm">
              {roots.data.map((root) => (
                <li key={root.path} className="flex items-center gap-2 truncate text-muted-foreground font-mono text-xs hover:text-foreground transition-colors">
                  <Folder className="h-3.5 w-3.5 shrink-0 text-primary" />
                  <span className="truncate">{root.path}</span>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex gap-2">
            <Input
              aria-label={t('capture.captureInbox.folderPathLabel')}
              value={path}
              onChange={(event) => setPath(event.target.value)}
              placeholder={t('capture.captureInbox.folderPathPlaceholder')}
              className="font-mono text-xs rounded-xl"
            />
            <Button
              type="button"
              variant="secondary"
              disabled={!path.trim() || actions.addRoot.isPending}
              onClick={() => void addRoot()}
              className="shrink-0 rounded-xl duration-150"
            >
              <FolderPlus className="mr-2 h-4 w-4" />
              {t('common.add')}
            </Button>
          </div>
        </div>
      </div>

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-foreground">{t('capture.captureInbox.inbox')}</h2>
          <span className="text-xs text-muted-foreground font-medium">
            {t('capture.captureInbox.itemsCount', { count: items.data?.length ?? 0 })}
          </span>
        </div>

        {items.isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t('capture.captureInbox.loading')}</p>
        ) : items.isError ? (
          <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            {t('capture.captureInbox.loadError')}
          </p>
        ) : items.data?.length ? (
          <Card className="divide-y border">
            <div className="p-4 space-y-3">
              {items.data.map((item) => (
                <CaptureItemRow
                  key={item.id ?? `${item.root_path}:${item.relative_path}`}
                  item={item}
                  showVisualCover={showVisualCover}
                />
              ))}
            </div>
          </Card>
        ) : (
          <div className="rounded-lg border border-dashed border-border p-8 text-center">
            <p className="text-sm font-medium text-foreground">{t('capture.captureInbox.emptyTitle')}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {t('capture.captureInbox.emptyDesc')}
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
