'use client'

import { useState } from 'react'
import { FileText, Folder, Hash, Network, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { TurnIntoPodcastAction } from '@/components/podcasts/TurnIntoPodcastAction'
import type { KnowledgeBookmark, KnowledgeBookmarkFolder, UpdateBookmarkCommand } from '@/lib/api/knowledge-navigation'
import { KNOWLEDGE_TARGET_STATE_KEYS, enumLabel } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'
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
  const { t } = useTranslation()
  return (
    <ul className="space-y-1" aria-label={t('knowledge.knowledgeBookmarksPanel.folders')}>
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
              label={t('knowledge.knowledgeBookmarksPanel.turnFolderIntoPodcast')}
              onOpen={onOpenPodcast}
            />
            {onDeleteFolder && <Button type="button" size="sm" variant="ghost" onClick={() => onRequestDelete(folder)}>{t('knowledge.knowledgeBookmarksPanel.deleteFolder')}</Button>}
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
  const { t } = useTranslation()
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
      setUpdateError(t('knowledge.knowledgeBookmarksPanel.updateConflict'))
    }
  }
  return (
    <section aria-label={t('knowledge.knowledgeBookmarksPanel.library')} className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t('knowledge.knowledgeBookmarksPanel.library')}</h2>
        <Button type="button" size="sm" variant="ghost" onClick={() => onSelectFolder?.(null)}>{t('knowledge.knowledgeBookmarksPanel.allBookmarks')}</Button>
      </div>
      {folders.length > 0 && <FolderTree folders={folders} onSelectFolder={onSelectFolder} onDeleteFolder={onDeleteFolder} onRequestDelete={setFolderToDelete} onOpenPodcast={openPodcastReview} />}
      <div className="flex flex-wrap gap-1" aria-label={t('knowledge.knowledgeBookmarksPanel.tagsLabel')}>
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
                    <Badge variant="outline">{isExternal ? t('knowledge.navigation.externalReadOnly') : t('knowledge.navigation.appOwned')}</Badge>
                    <Badge variant={available ? 'secondary' : 'outline'}>{bookmark.targetState ? enumLabel(t, KNOWLEDGE_TARGET_STATE_KEYS, bookmark.targetState) : t('knowledge.knowledgeBookmarksPanel.unavailableState')}</Badge>
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {available && <Button type="button" size="sm" onClick={() => void onOpen(bookmark)}>{t('knowledge.knowledgeBookmarksPanel.open', { label: bookmark.displayLabel })}</Button>}
                <TurnIntoPodcastAction
                  selection={{
                    kind: 'knowledge_collection',
                    collectionKind: 'bookmark',
                    collectionId: bookmark.id,
                  }}
                  destination="quick"
                  disabledReason={available ? undefined : t('knowledge.knowledgeBookmarksPanel.targetStateReason', { state: bookmark.targetState ? enumLabel(t, KNOWLEDGE_TARGET_STATE_KEYS, bookmark.targetState) : t('knowledge.knowledgeBookmarksPanel.unavailableState') })}
                  onOpen={openPodcastReview}
                />
                {!available && <Button type="button" size="sm" variant="outline" onClick={() => beginEdit(bookmark, true)}>{t('knowledge.knowledgeBookmarksPanel.editTarget', { label: bookmark.displayLabel })}</Button>}
                {available && <Button type="button" size="sm" variant="outline" aria-label={t('knowledge.knowledgeBookmarksPanel.editBookmarkAria', { label: bookmark.displayLabel })} onClick={() => beginEdit(bookmark, false)}>{t('knowledge.knowledgeBookmarksPanel.editBookmark')}</Button>}
                <Button type="button" size="sm" variant="ghost" aria-label={t('knowledge.knowledgeBookmarksPanel.deleteBookmarkAria', { label: bookmark.displayLabel })} onClick={() => onDelete(bookmark)}>{t('common.delete')}</Button>
              </div>
            </li>
          )
        })}
      </ul>
      {editing && <section aria-label={editing.target ? t('knowledge.knowledgeBookmarksPanel.editTargetSection') : t('knowledge.knowledgeBookmarksPanel.editMetadata')} className="rounded-md border p-3">
        <p className="text-sm font-medium">{editing.target ? t('knowledge.knowledgeBookmarksPanel.repairTarget') : t('knowledge.knowledgeBookmarksPanel.editMetadata')}</p>
        {editing.target ? <>
          <p className="mt-1 text-sm text-muted-foreground">{t('knowledge.knowledgeBookmarksPanel.repairNote')}</p>
          {(editing.bookmark.target.kind === 'document' || editing.bookmark.target.kind === 'block' || editing.bookmark.target.kind === 'graph') && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-document">{t('knowledge.knowledgeBookmarksPanel.targetDocumentId')}</label>
            <input id="bookmark-target-document" value={targetDocumentId} onChange={(event) => { const value = event.target.value; setTargetDocumentId(value); setTargetDraft((current) => current?.kind === 'document' ? { ...current, documentId: value } : current?.kind === 'block' ? { ...current, documentId: value } : current?.kind === 'graph' ? { ...current, rootDocumentId: value || null } : current) }} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'block' && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-block">{t('knowledge.knowledgeBookmarksPanel.targetBlockId')}</label>
            <input id="bookmark-target-block" value={targetDraft?.kind === 'block' ? targetDraft.blockId : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'block' ? { ...current, blockId: event.target.value } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-revision">{t('knowledge.knowledgeBookmarksPanel.sourceRevisionId')}</label>
            <input id="bookmark-target-revision" value={targetDraft?.kind === 'block' ? targetDraft.sourceRevisionId ?? '' : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'block' ? { ...current, sourceRevisionId: event.target.value || null } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'search' && <label className="mt-3 block text-sm" htmlFor="bookmark-target-query">{t('knowledge.knowledgeBookmarksPanel.searchQuery')}</label>}
          {editing.bookmark.target.kind === 'search' && <input id="bookmark-target-query" value={targetDraft?.kind === 'search' ? targetDraft.query : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, query: event.target.value } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />}
          {editing.bookmark.target.kind === 'search' && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-mode">{t('knowledge.knowledgeBookmarksPanel.searchMode')}</label>
            <select id="bookmark-target-search-mode" value={targetDraft?.kind === 'search' ? targetDraft.searchMode : 'text'} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, searchMode: event.target.value as 'exact' | 'text' | 'semantic' } : current)} className="mt-1 h-9 w-full rounded-md border px-2"><option value="exact">{t('knowledge.knowledgeBookmarksPanel.searchModeExact')}</option><option value="text">{t('knowledge.knowledgeBookmarksPanel.searchModeText')}</option><option value="semantic">{t('knowledge.knowledgeBookmarksPanel.searchModeSemantic')}</option></select>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-spaces">{t('knowledge.knowledgeBookmarksPanel.searchSpaceIds')}</label>
            <input id="bookmark-target-search-spaces" value={targetDraft?.kind === 'search' ? targetDraft.spaceIds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, spaceIds: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-authorities">{t('knowledge.knowledgeBookmarksPanel.searchAuthorityFilters')}</label>
            <input id="bookmark-target-search-authorities" value={targetDraft?.kind === 'search' ? targetDraft.authorityKinds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, authorityKinds: splitCsv(event.target.value) as typeof current.authorityKinds } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-search-tags">{t('knowledge.knowledgeBookmarksPanel.searchTags')}</label>
            <input id="bookmark-target-search-tags" value={targetDraft?.kind === 'search' ? targetDraft.tags.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'search' ? { ...current, tags: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'graph' && <>
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-graph-spaces">{t('knowledge.knowledgeBookmarksPanel.graphSpaceIds')}</label>
            <input id="bookmark-target-graph-spaces" value={targetDraft?.kind === 'graph' ? targetDraft.spaceIds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'graph' ? { ...current, spaceIds: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-graph-relations">{t('knowledge.knowledgeBookmarksPanel.graphRelationKinds')}</label>
            <input id="bookmark-target-graph-relations" value={targetDraft?.kind === 'graph' ? targetDraft.relationKinds.join(', ') : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'graph' ? { ...current, relationKinds: splitCsv(event.target.value) } : current)} className="mt-1 h-9 w-full rounded-md border px-2" />
            <label className="mt-3 block text-sm" htmlFor="bookmark-target-graph-viewport">{t('knowledge.knowledgeBookmarksPanel.graphViewport')}</label>
            <input id="bookmark-target-graph-viewport" value={targetDraft?.kind === 'graph' ? `${targetDraft.viewport.x}, ${targetDraft.viewport.y}, ${targetDraft.viewport.zoom}` : ''} onChange={(event) => { const [x, y, zoom] = splitCsv(event.target.value).map(Number); setTargetDraft((current) => current?.kind === 'graph' && [x, y, zoom].every(Number.isFinite) ? { ...current, viewport: { x, y, zoom } } : current) }} className="mt-1 h-9 w-full rounded-md border px-2" />
          </>}
          {editing.bookmark.target.kind === 'workspace' && <><label className="mt-3 block text-sm" htmlFor="bookmark-target-workspace">{t('knowledge.knowledgeBookmarksPanel.workspaceId')}</label><input id="bookmark-target-workspace" value={targetDraft?.kind === 'workspace' ? targetDraft.workspaceId : ''} onChange={(event) => setTargetDraft((current) => current?.kind === 'workspace' ? { ...current, workspaceId: event.target.value } : current)} className="mt-1 h-9 w-full rounded-md border px-2" /></>}
        </> : <>
          <label className="mt-3 block text-sm" htmlFor="bookmark-label">{t('knowledge.knowledgeBookmarksPanel.bookmarkLabel')}</label>
          <input id="bookmark-label" value={label} onChange={(event) => setLabel(event.target.value)} className="mt-1 h-9 w-full rounded-md border px-2" />
          <label className="mt-3 block text-sm" htmlFor="bookmark-tags">{t('knowledge.tags')}</label>
          <input id="bookmark-tags" value={tags} onChange={(event) => setTags(event.target.value)} className="mt-1 h-9 w-full rounded-md border px-2" />
        </>}
        {updateError && <p role="alert" className="mt-2 text-sm text-destructive">{updateError}</p>}
        <div className="mt-3 flex gap-2">
          <Button type="button" size="sm" onClick={() => void saveEdit()}>{editing.target ? t('knowledge.knowledgeBookmarksPanel.saveTargetRepair') : t('knowledge.knowledgeBookmarksPanel.saveMetadata')}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
        </div>
      </section>}
      {folderToDelete && <section aria-label={t('knowledge.knowledgeBookmarksPanel.confirmFolderDeletion')} className="rounded-md border border-destructive/40 p-3">
        <p className="text-sm font-medium">{t('knowledge.knowledgeBookmarksPanel.deleteFolderTitle', { name: folderToDelete.name })}</p>
        <p className="mt-1 text-sm text-muted-foreground">{t('knowledge.knowledgeBookmarksPanel.deleteFolderExplain')}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => { onDeleteFolder?.(folderToDelete, 'move_children'); setFolderToDelete(null) }}>{t('knowledge.knowledgeBookmarksPanel.moveChildren')}</Button>
          <Button type="button" size="sm" variant="destructive" onClick={() => { onDeleteFolder?.(folderToDelete, 'delete_tree'); setFolderToDelete(null) }}>{t('knowledge.knowledgeBookmarksPanel.deleteTree')}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setFolderToDelete(null)}>{t('common.cancel')}</Button>
        </div>
      </section>}
      {bookmarks.length === 0 && <p className="text-sm text-muted-foreground">{t('knowledge.knowledgeBookmarksPanel.empty')}</p>}
    </section>
  )
}
