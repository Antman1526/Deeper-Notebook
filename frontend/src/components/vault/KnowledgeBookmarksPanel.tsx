'use client'

import { useState } from 'react'
import { FileText, Folder, Hash, Network, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { KnowledgeBookmark, KnowledgeBookmarkFolder, UpdateBookmarkCommand } from '@/lib/api/knowledge-navigation'

interface KnowledgeBookmarksPanelProps {
  bookmarks: KnowledgeBookmark[]
  folders: KnowledgeBookmarkFolder[]
  onOpen: (bookmark: KnowledgeBookmark) => void
  onEdit: (bookmark: KnowledgeBookmark, editTarget: boolean) => void
  onUpdate?: (bookmark: KnowledgeBookmark, patch: Pick<UpdateBookmarkCommand, 'displayLabel' | 'tags' | 'target'>) => Promise<void>
  onDelete: (bookmark: KnowledgeBookmark) => void
  onSelectFolder?: (folderId: string | null) => void
  onDeleteFolder?: (folder: KnowledgeBookmarkFolder, policy: 'move_children' | 'delete_tree') => void
}

function TargetIcon({ kind }: { kind: KnowledgeBookmark['targetKind'] }) {
  const Icon = kind === 'search' ? Search : kind === 'graph' ? Network : FileText
  return <Icon aria-hidden="true" className="h-4 w-4" />
}

function FolderTree({ folders, onSelectFolder, onDeleteFolder, onRequestDelete }: Pick<KnowledgeBookmarksPanelProps, 'folders' | 'onSelectFolder' | 'onDeleteFolder'> & { onRequestDelete: (folder: KnowledgeBookmarkFolder) => void }) {
  return (
    <ul className="space-y-1" aria-label="Bookmark folders">
      {folders.map((folder) => (
        <li key={folder.id}>
          <div className="flex items-center gap-1">
            <Button type="button" size="sm" variant="ghost" className="justify-start" onClick={() => onSelectFolder?.(folder.id)}>
              <Folder aria-hidden="true" className="mr-1.5 h-4 w-4" />{folder.name}
            </Button>
            {onDeleteFolder && <Button type="button" size="sm" variant="ghost" onClick={() => onRequestDelete(folder)}>Delete folder</Button>}
          </div>
          {folder.children.length > 0 && <div className="ml-3 border-l pl-2"><FolderTree folders={folder.children} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} onRequestDelete={onRequestDelete} /></div>}
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
  onUpdate,
  onDelete,
  onSelectFolder,
  onDeleteFolder,
}: KnowledgeBookmarksPanelProps) {
  const [editing, setEditing] = useState<{ bookmark: KnowledgeBookmark; target: boolean } | null>(null)
  const [label, setLabel] = useState('')
  const [tags, setTags] = useState('')
  const [targetDocumentId, setTargetDocumentId] = useState('')
  const [updateError, setUpdateError] = useState('')
  const [folderToDelete, setFolderToDelete] = useState<KnowledgeBookmarkFolder | null>(null)
  const beginEdit = (bookmark: KnowledgeBookmark, target: boolean) => {
    setEditing({ bookmark, target })
    setLabel(bookmark.displayLabel)
    setTags(bookmark.tags.join(', '))
    setTargetDocumentId(bookmark.target.kind === 'document' || bookmark.target.kind === 'block'
      ? bookmark.target.documentId
      : bookmark.target.kind === 'graph' ? bookmark.target.rootDocumentId ?? '' : '')
    setUpdateError('')
    onEdit(bookmark, target)
  }
  const saveEdit = async () => {
    if (!editing || !onUpdate) return
    const normalizedTags = tags.split(',').map((tag) => tag.trim()).filter(Boolean)
    try {
      const target = editing.bookmark.target.kind === 'document'
        ? { kind: 'document' as const, documentId: targetDocumentId }
        : editing.bookmark.target.kind === 'block'
          ? { ...editing.bookmark.target, documentId: targetDocumentId }
          : editing.bookmark.target.kind === 'graph'
            ? { ...editing.bookmark.target, rootDocumentId: targetDocumentId || null }
            : editing.bookmark.target
      await onUpdate(editing.bookmark, editing.target
        ? { target }
        : { displayLabel: label.trim(), tags: normalizedTags })
      setEditing(null)
    } catch {
      setUpdateError('Bookmark update conflicted or could not be saved.')
    }
  }
  return (
    <section aria-label="Bookmark library" className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Bookmark library</h2>
        <Button type="button" size="sm" variant="ghost" onClick={() => onSelectFolder?.(null)}>All bookmarks</Button>
      </div>
      {folders.length > 0 && <FolderTree folders={folders} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} onRequestDelete={setFolderToDelete} />}
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
                {available && <Button type="button" size="sm" onClick={() => void onOpen(bookmark)}>Open {bookmark.displayLabel}</Button>}
                {!available && <Button type="button" size="sm" variant="outline" onClick={() => beginEdit(bookmark, true)}>Edit Target {bookmark.displayLabel}</Button>}
                {available && <Button type="button" size="sm" variant="outline" aria-label={`Edit bookmark ${bookmark.displayLabel}`} onClick={() => beginEdit(bookmark, false)}>Edit bookmark</Button>}
                <Button type="button" size="sm" variant="ghost" aria-label={`Delete bookmark ${bookmark.displayLabel}`} onClick={() => onDelete(bookmark)}>Delete</Button>
              </div>
            </li>
          )
        })}
      </ul>
      {editing && <section aria-label={editing.target ? 'Edit bookmark target' : 'Edit bookmark metadata'} className="rounded-md border p-3">
        <p className="text-sm font-medium">{editing.target ? 'Repair bookmark target' : 'Edit bookmark metadata'}</p>
        {editing.target ? <>
          <p className="mt-1 text-sm text-muted-foreground">This repair updates only the stored target reference; it never writes to the source document.</p>
          {(editing.bookmark.target.kind === 'document' || editing.bookmark.target.kind === 'block' || editing.bookmark.target.kind === 'graph') && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-document">Target document ID</label>
            <input id="bookmark-target-document" value={targetDocumentId} onChange={(event) => setTargetDocumentId(event.target.value)} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
        </> : <>
          <label className="mt-3 block text-sm" htmlFor="bookmark-label">Bookmark label</label>
          <input id="bookmark-label" value={label} onChange={(event) => setLabel(event.target.value)} className="mt-1 h-9 w-full rounded-md border px-2" />
          <label className="mt-3 block text-sm" htmlFor="bookmark-tags">Tags</label>
          <input id="bookmark-tags" value={tags} onChange={(event) => setTags(event.target.value)} className="mt-1 h-9 w-full rounded-md border px-2" />
        </>}
        {updateError && <p role="alert" className="mt-2 text-sm text-destructive">{updateError}</p>}
        <div className="mt-3 flex gap-2">
          <Button type="button" size="sm" onClick={() => void saveEdit()}>{editing.target ? 'Save target repair' : 'Save bookmark metadata'}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
        </div>
      </section>}
      {folderToDelete && <section aria-label="Confirm folder deletion" className="rounded-md border border-destructive/40 p-3">
        <p className="text-sm font-medium">Delete {folderToDelete.name}?</p>
        <p className="mt-1 text-sm text-muted-foreground">Move children keeps descendant bookmarks and folders. Delete tree permanently removes this folder and every descendant bookmark folder.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => { onDeleteFolder?.(folderToDelete, 'move_children'); setFolderToDelete(null) }}>Move children</Button>
          <Button type="button" size="sm" variant="destructive" onClick={() => { onDeleteFolder?.(folderToDelete, 'delete_tree'); setFolderToDelete(null) }}>Delete tree</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setFolderToDelete(null)}>Cancel</Button>
        </div>
      </section>}
      {bookmarks.length === 0 && <p className="text-sm text-muted-foreground">No bookmarks match these filters.</p>}
    </section>
  )
}
