'use client'

import { useState } from 'react'
import { FileText, Folder, Hash, Network, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { TurnIntoPodcastAction } from '@/components/podcasts/TurnIntoPodcastAction'
import type { KnowledgeBookmark, KnowledgeBookmarkFolder, UpdateBookmarkCommand } from '@/lib/api/knowledge-navigation'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

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

function splitCsv(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function FolderTree({ folders, onSelectFolder, onDeleteFolder, onRequestDelete, onOpenPodcast }: Pick<KnowledgeBookmarksPanelProps, 'folders' | 'onSelectFolder' | 'onDeleteFolder'> & { onRequestDelete: (folder: KnowledgeBookmarkFolder) => void; onOpenPodcast: ReturnType<typeof usePodcastStudioStore.getState>['open'] }) {
  return (
    <ul className="space-y-1" aria-label="Bookmark folders">
      {folders.map((folder) => (
        <li key={folder.id}>
          <div className="flex items-center gap-1">
            <Button type="button" size="sm" variant="ghost" className="justify-start" onClick={() => onSelectFolder?.(folder.id)}>
              <Folder aria-hidden="true" className="mr-1.5 h-4 w-4" />{folder.name}
            </Button>
            <TurnIntoPodcastAction
              selection={{
                kind: 'knowledge_collection',
                collectionKind: 'folder',
                collectionId: folder.id,
              }}
              destination="quick"
              label="Turn folder into podcast"
              onOpen={onOpenPodcast}
            />
            {onDeleteFolder && <Button type="button" size="sm" variant="ghost" onClick={() => onRequestDelete(folder)}>Delete folder</Button>}
          </div>
          {folder.children.length > 0 && <div className="ml-3 border-l pl-2"><FolderTree folders={folder.children} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} onRequestDelete={onRequestDelete} onOpenPodcast={onOpenPodcast} /></div>}
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
  const openPodcastReview = usePodcastStudioStore((state) => state.open)
  const [editing, setEditing] = useState<{ bookmark: KnowledgeBookmark; target: boolean } | null>(null)
  const [label, setLabel] = useState('')
  const [tags, setTags] = useState('')
  const [targetDocumentId, setTargetDocumentId] = useState('')
  const [targetDraft, setTargetDraft] = useState<KnowledgeBookmark['target'] | null>(null)
  const [updateError, setUpdateError] = useState('')
  const [folderToDelete, setFolderToDelete] = useState<KnowledgeBookmarkFolder | null>(null)
  const beginEdit = (bookmark: KnowledgeBookmark, target: boolean) => {
    setEditing({ bookmark, target })
    setLabel(bookmark.displayLabel)
    setTags(bookmark.tags.join(', '))
    setTargetDocumentId(bookmark.target.kind === 'document' || bookmark.target.kind === 'block'
      ? bookmark.target.documentId
      : bookmark.target.kind === 'graph' ? bookmark.target.rootDocumentId ?? '' : '')
    setTargetDraft(bookmark.target)
    setUpdateError('')
    onEdit(bookmark, target)
  }
  const saveEdit = async () => {
    if (!editing || !onUpdate) return
    const normalizedTags = tags.split(',').map((tag) => tag.trim()).filter(Boolean)
    try {
      const target = editing.target ? targetDraft ?? editing.bookmark.target : editing.bookmark.target.kind === 'document'
        ? { kind: 'document' as const, documentId: targetDocumentId }
        : editing.bookmark.target.kind === 'block'
          ? { ...editing.bookmark.target, documentId: targetDocumentId }
          : editing.bookmark.target.kind === 'graph'
            ? { ...editing.bookmark.target, rootDocumentId: targetDocumentId || null }
            : targetDraft ?? editing.bookmark.target
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
      {folders.length > 0 && <FolderTree folders={folders} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} onRequestDelete={setFolderToDelete} onOpenPodcast={openPodcastReview} />}
      <div className="flex flex-wrap gap-1" aria-label="Bookmark tags">
        {[...new Set(bookmarks.flatMap((bookmark) => bookmark.tags))].map((tag) => <Badge key={tag} variant="outline"><Hash aria-hidden="true" className="mr-1 h-3 w-3" />{tag}</Badge>)}
      </div>
      <ul className="space-y-2">
        {bookmarks.map((bookmark) => {
          const requiresDescriptor = bookmark.target.kind === 'document'
            || bookmark.target.kind === 'block'
            || bookmark.target.kind === 'graph'
          const available = bookmark.targetState === 'available'
            && (!requiresDescriptor || Boolean(bookmark.targetDocument))
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
                <TurnIntoPodcastAction
                  selection={{
                    kind: 'knowledge_collection',
                    collectionKind: 'bookmark',
                    collectionId: bookmark.id,
                  }}
                  destination="quick"
                  disabledReason={available ? undefined : `Bookmark target is ${bookmark.targetState || 'unavailable'}.`}
                  onOpen={openPodcastReview}
                />
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
            <input id="bookmark-target-document" value={targetDocumentId} onChange={(event) => { const value = event.target.value; setTargetDocumentId(value); setTargetDraft((current) => current?.kind === 'document' ? { ...current, documentId: value } : current?.kind === 'block' ? { ...current, documentId: value } : current?.kind === 'graph' ? { ...current, rootDocumentId: value || null } : current) }} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'block' && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-block">Target block ID</label>
            <input id="bookmark-target-block" value={targetDraft?.kind === 'block' ? targetDraft.blockId : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'block' ? { ...current, blockId: event.target.value } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-revision">Source revision ID</label>
            <input id="bookmark-target-revision" value={targetDraft?.kind === 'block' ? targetDraft.sourceRevisionId ?? '' : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'block' ? { ...current, sourceRevisionId: event.target.value || null } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'search' && <label className="mt-3 block text-sm" htmlFor="bookmark-target-query">Search query</label>}
          {editing.bookmark.target.kind === 'search' && <input id="bookmark-target-query" value={targetDraft?.kind === 'search' ? targetDraft.query : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, query: event.target.value } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />}
          {editing.bookmark.target.kind === 'search' && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-mode">Search mode</label>
            <select id="bookmark-target-search-mode" value={targetDraft?.kind === 'search' ? targetDraft.searchMode : 'text'} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, searchMode: event.target.value as 'exact' | 'text' | 'semantic' } : current)} className="mt-1 h-9 w-full rounded-md border px-2"><option value="exact">exact</option><option value="text">text</option><option value="semantic">semantic</option></select>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-spaces">Search space IDs</label>
            <input id="bookmark-target-search-spaces" value={targetDraft?.kind === 'search' ? targetDraft.spaceIds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, spaceIds: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-authorities">Search authority filters</label>
            <input id="bookmark-target-search-authorities" value={targetDraft?.kind === 'search' ? targetDraft.authorityKinds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, authorityKinds: splitCsv(event.target.value) as typeof current.authorityKinds } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-tags">Search tags</label>
            <input id="bookmark-target-search-tags" value={targetDraft?.kind === 'search' ? targetDraft.tags.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, tags: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'graph' && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-graph-spaces">Graph space IDs</label>
            <input id="bookmark-target-graph-spaces" value={targetDraft?.kind === 'graph' ? targetDraft.spaceIds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'graph' ? { ...current, spaceIds: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-graph-relations">Graph relation kinds</label>
            <input id="bookmark-target-graph-relations" value={targetDraft?.kind === 'graph' ? targetDraft.relationKinds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'graph' ? { ...current, relationKinds: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-graph-viewport">Graph viewport</label>
            <input id="bookmark-target-graph-viewport" value={targetDraft?.kind === 'graph' ? `${targetDraft.viewport.x}, ${targetDraft.viewport.y}, ${targetDraft.viewport.zoom}` : ''} onChange={(event) => { const [x, y, zoom] = splitCsv(event.target.value).map(Number); setTargetDraft((current) => current?.kind === 'graph' && [x, y, zoom].every(Number.isFinite) ? { ...current, viewport: { x, y, zoom } } : current) }} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'workspace' && <><label className="mt-3 block text-sm" htmlFor="bookmark-target-workspace">Workspace ID</label><input id="bookmark-target-workspace" value={targetDraft?.kind === 'workspace' ? targetDraft.workspaceId : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'workspace' ? { ...current, workspaceId: event.target.value } : current)} className="mt-1 h-9 w-full rounded-md border px-2" /></>}
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
        <p className="mt-1 text-sm text-muted-foreground">Move children keeps descendant bookmarks and folders. Delete tree permanently deletes this folder, descendant folders, and their contained bookmark metadata; it never edits source documents.</p>
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
