'use client'

import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { TurnIntoPodcastAction } from '@/components/podcasts/TurnIntoPodcastAction'
import type { NamedKnowledgeWorkspaceSummary } from '@/lib/api/knowledge-navigation'
import { useTranslation } from '@/lib/hooks/use-translation'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

interface KnowledgeWorkspacesPanelProps {
  workspaces: NamedKnowledgeWorkspaceSummary[]
  onSaveCurrentAs: (name: string) => Promise<void>
  onOpen: (workspace: NamedKnowledgeWorkspaceSummary) => Promise<void>
  onRename: (workspace: NamedKnowledgeWorkspaceSummary, name: string) => Promise<void>
  onDuplicate: (workspace: NamedKnowledgeWorkspaceSummary, name: string) => Promise<void>
  onReplaceWithCurrent: (workspace: NamedKnowledgeWorkspaceSummary) => Promise<void>
  onDelete: (workspace: NamedKnowledgeWorkspaceSummary) => Promise<void>
  onRefresh: () => Promise<unknown>
  commandIntent?: { id: number; kind: 'save' | 'replace' } | null
}

type EditMode = 'save' | 'rename' | 'duplicate' | null

function isConflict(error: unknown): boolean {
  return typeof error === 'object' && error !== null
    && 'response' in error
    && typeof error.response === 'object'
    && error.response !== null
    && 'status' in error.response
    && error.response.status === 409
}

export function KnowledgeWorkspacesPanel({
  workspaces,
  onSaveCurrentAs,
  onOpen,
  onRename,
  onDuplicate,
  onReplaceWithCurrent,
  onDelete,
  onRefresh,
  commandIntent = null,
}: KnowledgeWorkspacesPanelProps) {
  const { t } = useTranslation()
  const openPodcastReview = usePodcastStudioStore((state) => state.open)
  const [editMode, setEditMode] = useState<EditMode>(null)
  const [editing, setEditing] = useState<NamedKnowledgeWorkspaceSummary | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [selectingReplacement, setSelectingReplacement] = useState(false)
  const commandIntentId = commandIntent?.id ?? null
  const commandIntentKind = commandIntent?.kind ?? null

  useEffect(() => {
    if (!commandIntentKind) return
    if (commandIntentKind === 'save') begin('save')
    else setSelectingReplacement(true)
  }, [commandIntentId, commandIntentKind])

  const begin = (mode: Exclude<EditMode, null>, workspace?: NamedKnowledgeWorkspaceSummary) => {
    setEditMode(mode)
    setEditing(workspace ?? null)
    setName(mode === 'rename' ? workspace?.name ?? '' : '')
    setError('')
  }
  const close = (force = false) => {
    if (pending && !force) return
    setEditMode(null)
    setEditing(null)
    setName('')
    setError('')
  }
  const submit = async () => {
    const trimmedName = name.trim()
    if (!editMode || !trimmedName) return
    setPending(true)
    setError('')
    try {
      if (editMode === 'save') await onSaveCurrentAs(trimmedName)
      else if (editMode === 'rename' && editing) await onRename(editing, trimmedName)
      else if (editMode === 'duplicate' && editing) await onDuplicate(editing, trimmedName)
      close(true)
    } catch (cause) {
      if (isConflict(cause)) {
        setError(t('knowledge.knowledgeWorkspacesPanel.conflict'))
        void onRefresh()
      } else {
        setError(t('knowledge.knowledgeWorkspacesPanel.saveFailed'))
      }
    } finally {
      setPending(false)
    }
  }
  const perform = async (action: () => Promise<void>) => {
    setError('')
    setPending(true)
    try {
      await action()
    } catch (cause) {
      if (isConflict(cause)) {
        setError(t('knowledge.knowledgeWorkspacesPanel.conflict'))
        void onRefresh()
      } else {
        setError(t('knowledge.knowledgeWorkspacesPanel.updateFailed'))
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-label={t('knowledge.knowledgeWorkspacesPanel.saved')} className="space-y-3">
      <div className="rounded-md border p-3">
        <h2 className="font-medium">{t('knowledge.knowledgeWorkspacesPanel.currentSession')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('knowledge.knowledgeWorkspacesPanel.autosaved')}</p>
        <Button type="button" size="sm" className="mt-3" onClick={() => begin('save')}>{t('knowledge.knowledgeWorkspacesPanel.saveCurrentAs')}</Button>
      </div>
      {selectingReplacement && <p role="status" className="text-sm text-muted-foreground">{t('knowledge.knowledgeWorkspacesPanel.selectReplacement')}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {editMode && <form aria-label={t('knowledge.knowledgeWorkspacesPanel.editor')} className="rounded-md border p-3" onSubmit={(event) => { event.preventDefault(); void submit() }}>
        <label className="block text-sm font-medium" htmlFor="workspace-name">{t('knowledge.knowledgeWorkspacesPanel.nameLabel')}</label>
        <input id="workspace-name" value={name} onChange={(event) => setName(event.target.value)} autoFocus className="mt-1 h-9 w-full rounded-md border px-2" />
        <div className="mt-3 flex gap-2">
          <Button type="submit" size="sm" disabled={!name.trim() || pending}>
            {editMode === 'rename' ? t('knowledge.knowledgeWorkspacesPanel.saveRename') : editMode === 'duplicate' ? t('knowledge.knowledgeWorkspacesPanel.duplicateWorkspace') : t('knowledge.knowledgeWorkspacesPanel.saveWorkspace')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => close()} disabled={pending}>{t('common.cancel')}</Button>
        </div>
      </form>}
      <ul className="space-y-2">
        {workspaces.map((workspace) => <li key={workspace.id} className="rounded-md border p-3">
          <p className="font-medium">{workspace.name}</p>
          <p className="text-xs text-muted-foreground">{t('knowledge.knowledgeWorkspacesPanel.revision', { revision: workspace.revision })}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={() => void perform(() => onOpen(workspace))} disabled={pending}>{t('knowledge.knowledgeWorkspacesPanel.open', { name: workspace.name })}</Button>
            <TurnIntoPodcastAction
              selection={{
                kind: 'knowledge_collection',
                collectionKind: 'workspace',
                collectionId: workspace.id,
              }}
              destination="quick"
              disabledReason={pending ? t('knowledge.knowledgeWorkspacesPanel.actionInProgress') : undefined}
              onOpen={openPodcastReview}
            />
            <Button type="button" size="sm" variant="outline" onClick={() => begin('rename', workspace)} disabled={pending}>{t('knowledge.knowledgeWorkspacesPanel.rename', { name: workspace.name })}</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => begin('duplicate', workspace)} disabled={pending}>{t('knowledge.knowledgeWorkspacesPanel.duplicate', { name: workspace.name })}</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => { setSelectingReplacement(false); void perform(() => onReplaceWithCurrent(workspace)) }} disabled={pending}>{t('knowledge.knowledgeWorkspacesPanel.replaceWithCurrent')}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void perform(() => onDelete(workspace))} disabled={pending}>{t('knowledge.knowledgeWorkspacesPanel.delete', { name: workspace.name })}</Button>
          </div>
        </li>)}
      </ul>
    </section>
  )
}
