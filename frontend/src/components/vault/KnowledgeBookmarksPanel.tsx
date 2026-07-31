'use client'

import { FileText, Folder, Hash, Network, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { KnowledgeBookmark, KnowledgeBookmarkFolder, KnowledgeOpenDescriptor } from '@/lib/api/knowledge-navigation'

interface KnowledgeBookmarksPanelProps {
  bookmarks: KnowledgeBookmark[]
  folders: KnowledgeBookmarkFolder[]
  onOpen: (document: KnowledgeOpenDescriptor) => void
  onEdit: (bookmark: KnowledgeBookmark, editTarget: boolean) => void
  onDelete: (bookmark: KnowledgeBookmark) => void
  onSelectFolder?: (folderId: string | null) => void
  onDeleteFolder?: (folder: KnowledgeBookmarkFolder, policy: 'move_children' | 'delete_tree') => void
}

function TargetIcon({ kind }: { kind: KnowledgeBookmark['targetKind'] }) {
  const Icon = kind === 'search' ? Search : kind === 'graph' ? Network : FileText
  return <Icon aria-hidden="true" className="h-4 w-4" />
}

function FolderTree({ folders, onSelectFolder, onDeleteFolder }: Pick<KnowledgeBookmarksPanelProps, 'folders' | 'onSelectFolder' | 'onDeleteFolder'>) {
  return (
    <ul className="space-y-1" aria-label="Bookmark folders">
      {folders.map((folder) => (
        <li key={folder.id}>
          <div className="flex items-center gap-1">
            <Button type="button" size="sm" variant="ghost" className="justify-start" onClick={() => onSelectFolder?.(folder.id)}>
              <Folder aria-hidden="true" className="mr-1.5 h-4 w-4" />{folder.name}
            </Button>
            {onDeleteFolder && <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground">Delete folder</summary>
              <div className="flex gap-1 pt-1">
                <Button type="button" size="sm" variant="outline" onClick={() => onDeleteFolder(folder, 'move_children')}>Move children</Button>
                <Button type="button" size="sm" variant="destructive" onClick={() => onDeleteFolder(folder, 'delete_tree')}>Delete tree</Button>
              </div>
            </details>}
          </div>
          {folder.children.length > 0 && <div className="ml-3 border-l pl-2"><FolderTree folders={folder.children} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} /></div>}
        </li>
      ))}
    </ul>
  )
}

export function KnowledgeBookmarksPanel({
  bookmarks,
  folders,
  onOpen,
  onEdit,
  onDelete,
  onSelectFolder,
  onDeleteFolder,
}: KnowledgeBookmarksPanelProps) {
  return (
    <section aria-label="Bookmark library" className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Bookmark library</h2>
        <Button type="button" size="sm" variant="ghost" onClick={() => onSelectFolder?.(null)}>All bookmarks</Button>
      </div>
      {folders.length > 0 && <FolderTree folders={folders} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} />}
      <div className="flex flex-wrap gap-1" aria-label="Bookmark tags">
        {[...new Set(bookmarks.flatMap((bookmark) => bookmark.tags))].map((tag) => <Badge key={tag} variant="outline"><Hash aria-hidden="true" className="mr-1 h-3 w-3" />{tag}</Badge>)}
      </div>
      <ul className="space-y-2">
        {bookmarks.map((bookmark) => {
          const available = bookmark.targetState === 'available' && Boolean(bookmark.targetDocument)
          const isExternal = bookmark.authorityKind === 'external_read_only'
          return (
            <li key={bookmark.id} className="rounded-md border p-3">
              <div className="flex items-start gap-2">
                <TargetIcon kind={bookmark.targetKind} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{bookmark.displayLabel}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <Badge variant="outline">{isExternal ? 'External read-only' : 'App-owned'}</Badge>
                    <Badge variant={available ? 'secondary' : 'outline'}>{bookmark.targetState || 'unavailable'}</Badge>
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {available && bookmark.targetDocument && <Button type="button" size="sm" onClick={() => onOpen(bookmark.targetDocument!)}>Open {bookmark.displayLabel}</Button>}
                {!available && <Button type="button" size="sm" variant="outline" onClick={() => onEdit(bookmark, true)}>Edit Target {bookmark.displayLabel}</Button>}
                {available && <Button type="button" size="sm" variant="outline" aria-label={`Edit bookmark ${bookmark.displayLabel}`} onClick={() => onEdit(bookmark, false)}>Edit bookmark</Button>}
                <Button type="button" size="sm" variant="ghost" aria-label={`Delete bookmark ${bookmark.displayLabel}`} onClick={() => onDelete(bookmark)}>Delete</Button>
              </div>
            </li>
          )
        })}
      </ul>
      {bookmarks.length === 0 && <p className="text-sm text-muted-foreground">No bookmarks match these filters.</p>}
    </section>
  )
}
