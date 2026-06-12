// v0.7.105 — Directory picker dialog used by export flows.
//
// Two-pane layout:
//   - Left: shortcuts (home / desktop / documents / downloads / default
//     exports) + the parent-of-current entry.
//   - Right: entries in the current directory.
// User can type a path manually, click into a folder, mkdir, then
// confirm. The picker doesn't auto-create the path on confirm — the
// caller chooses what to do with it.
'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronLeft, File, Folder, FolderPlus, Home } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useFsHome, useFsList, useFsMkdir } from '@/lib/hooks/use-fs'
import { useToast } from '@/lib/hooks/use-toast'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'

interface DirectoryPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialPath?: string
  /** Returns the user-confirmed directory or file path. */
  onSelect: (path: string) => void
  // v0.7.119 — When 'any', also list files in the entries pane and
  // let the user pick a file (used by Import for .zip / .md targets).
  // Default 'dir' preserves the original export-flow behavior.
  selectionMode?: 'dir' | 'any'
}

export function DirectoryPicker({
  open,
  onOpenChange,
  initialPath,
  onSelect,
  selectionMode = 'dir',
}: DirectoryPickerProps) {
  const { t } = useTranslation()
  const { toast } = useToast()

  const homeQuery = useFsHome(open)
  const [currentPath, setCurrentPath] = useState<string | null>(initialPath ?? null)
  const [pathInput, setPathInput] = useState<string>(initialPath ?? '')
  const [showNewFolderInput, setShowNewFolderInput] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')

  // Pick a sensible starting directory once the home payload arrives.
  useEffect(() => {
    if (!open) return
    if (currentPath) return
    if (!homeQuery.data) return
    const fallback = homeQuery.data.home
    setCurrentPath(fallback)
    setPathInput(fallback)
  }, [open, currentPath, homeQuery.data])

  // Reset transient state when the dialog closes.
  useEffect(() => {
    if (!open) {
      setShowNewFolderInput(false)
      setNewFolderName('')
      if (initialPath) {
        setCurrentPath(initialPath)
        setPathInput(initialPath)
      } else {
        setCurrentPath(null)
        setPathInput('')
      }
    }
  }, [open, initialPath])

  const listQuery = useFsList(currentPath, {
    only: selectionMode === 'any' ? 'all' : 'dirs',
    enabled: open,
  })

  const mkdirMutation = useFsMkdir()

  const navigate = useCallback((path: string) => {
    setCurrentPath(path)
    setPathInput(path)
    setShowNewFolderInput(false)
    setNewFolderName('')
  }, [])

  const handleGoUp = () => {
    if (listQuery.data?.parent) {
      navigate(listQuery.data.parent)
    }
  }

  const handlePathInputBlur = () => {
    const trimmed = pathInput.trim()
    if (trimmed && trimmed !== currentPath) {
      navigate(trimmed)
    }
  }

  const handlePathInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handlePathInputBlur()
    }
  }

  const handleCreateFolder = async () => {
    const name = newFolderName.trim()
    if (!name || !currentPath) return
    const target = `${currentPath.replace(/\/+$/, '')}/${name}`
    try {
      const result = await mkdirMutation.mutateAsync(target)
      setShowNewFolderInput(false)
      setNewFolderName('')
      navigate(result.path)
    } catch (error: unknown) {
      toast({
        title: t('filesystem.cannotCreateFolder'),
        description: t(getApiErrorKey(error, t('common.error'))),
        variant: 'destructive',
      })
    }
  }

  const handleConfirm = () => {
    if (!currentPath) return
    onSelect(currentPath)
    onOpenChange(false)
  }

  const shortcuts = useMemo(() => {
    if (!homeQuery.data) return []
    const items: Array<{ label: string; path: string }> = []
    items.push({ label: t('filesystem.home'), path: homeQuery.data.home })
    if (homeQuery.data.desktop)
      items.push({ label: t('filesystem.desktop'), path: homeQuery.data.desktop })
    if (homeQuery.data.documents)
      items.push({ label: t('filesystem.documents'), path: homeQuery.data.documents })
    if (homeQuery.data.downloads)
      items.push({ label: t('filesystem.downloads'), path: homeQuery.data.downloads })
    items.push({
      label: t('filesystem.defaultExports'),
      path: homeQuery.data.default_exports,
    })
    return items
  }, [homeQuery.data, t])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('filesystem.pickDirectory')}</DialogTitle>
          <DialogDescription>{t('filesystem.pickDirectoryDesc')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="dir-picker-path">{t('filesystem.path')}</Label>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="icon"
                onClick={handleGoUp}
                disabled={!listQuery.data?.parent}
                aria-label={t('filesystem.goUp')}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Input
                id="dir-picker-path"
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                onBlur={handlePathInputBlur}
                onKeyDown={handlePathInputKeyDown}
                placeholder={t('filesystem.pathPlaceholder')}
                className="flex-1"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 border rounded-md p-3 bg-muted/30">
            {/* Shortcuts */}
            <div className="col-span-1 space-y-1">
              {homeQuery.isLoading ? (
                <div className="flex items-center justify-center py-4">
                  <LoadingSpinner size="sm" />
                </div>
              ) : (
                shortcuts.map((shortcut) => (
                  <button
                    key={shortcut.path}
                    type="button"
                    onClick={() => navigate(shortcut.path)}
                    className="w-full text-left text-sm px-2 py-1.5 rounded hover:bg-accent flex items-center gap-2"
                  >
                    <Home className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="truncate">{shortcut.label}</span>
                  </button>
                ))
              )}
            </div>

            {/* Entries */}
            <div className="col-span-2">
              <ScrollArea className="h-64 rounded-md border bg-background">
                {listQuery.isLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <LoadingSpinner size="sm" />
                  </div>
                ) : listQuery.error ? (
                  <p className="text-sm text-destructive p-3">
                    {t('filesystem.loadFailed')}
                  </p>
                ) : !listQuery.data || listQuery.data.entries.length === 0 ? (
                  <p className="text-sm text-muted-foreground p-3">
                    {t('filesystem.emptyDirectory')}
                  </p>
                ) : (
                  <div className="p-1">
                    {listQuery.data.truncated && (
                      <p className="text-xs text-amber-700 dark:text-amber-400 px-2 py-1 mb-1">
                        {t('filesystem.truncated').replace(
                          '{count}',
                          String(listQuery.data.entries.length)
                        )}
                      </p>
                    )}
                    {listQuery.data.entries.map((entry) => {
                      // v0.7.119 — In 'any' selectionMode, single-clicking
                      // a file picks it (no nested navigation possible).
                      // Folders still navigate as before.
                      const isFile = !entry.is_dir
                      const handleSelectFile = () => {
                        if (!isFile) return
                        onSelect(entry.path)
                        onOpenChange(false)
                      }
                      return (
                        <button
                          key={entry.path}
                          type="button"
                          onDoubleClick={() =>
                            entry.is_dir ? navigate(entry.path) : handleSelectFile()
                          }
                          onClick={() =>
                            entry.is_dir ? navigate(entry.path) : handleSelectFile()
                          }
                          className="w-full text-left text-sm px-2 py-1.5 rounded hover:bg-accent flex items-center gap-2"
                        >
                          {entry.is_dir ? (
                            <Folder className="h-3.5 w-3.5 text-muted-foreground" />
                          ) : (
                            <File className="h-3.5 w-3.5 text-muted-foreground" />
                          )}
                          <span className="truncate">{entry.name}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>

          {showNewFolderInput ? (
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Label htmlFor="new-folder-name">{t('filesystem.newFolderPrompt')}</Label>
                <Input
                  id="new-folder-name"
                  autoFocus
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleCreateFolder()
                    }
                  }}
                />
              </div>
              <Button
                onClick={handleCreateFolder}
                disabled={!newFolderName.trim() || mkdirMutation.isPending}
              >
                {t('filesystem.create')}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowNewFolderInput(false)
                  setNewFolderName('')
                }}
              >
                {t('filesystem.cancel')}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowNewFolderInput(true)}
              disabled={!currentPath}
            >
              <FolderPlus className="h-4 w-4 mr-2" />
              {t('filesystem.newFolder')}
            </Button>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('filesystem.cancel')}
          </Button>
          <Button onClick={handleConfirm} disabled={!currentPath}>
            {t('filesystem.useThisLocation')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
