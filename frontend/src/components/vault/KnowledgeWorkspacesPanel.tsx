'use client'

import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { NamedKnowledgeWorkspaceSummary } from '@/lib/api/knowledge-navigation'

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
  const [editMode, setEditMode] = useState<EditMode>(null)
  const [editing, setEditing] = useState<NamedKnowledgeWorkspaceSummary | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [selectingReplacement, setSelectingReplacement] = useState(false)

  useEffect(() => {
    if (!commandIntent) return
    if (commandIntent.kind === 'save') begin('save')
    else setSelectingReplacement(true)
  }, [commandIntent?.id])

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
        setError('Workspace changed elsewhere. Refreshing its latest revision; review and try again.')
        void onRefresh()
      } else {
        setError('Workspace could not be saved. Check the knowledge engine and try again.')
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
        setError('Workspace changed elsewhere. Refreshing its latest revision; review and try again.')
        void onRefresh()
      } else {
        setError('Workspace could not be updated. Check the knowledge engine and try again.')
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-label="Saved workspaces" className="space-y-3">
      <div className="rounded-md border p-3">
        <h2 className="font-medium">Current Session</h2>
        <p className="mt-1 text-sm text-muted-foreground">Autosaved locally in this knowledge workspace.</p>
        <Button type="button" size="sm" className="mt-3" onClick={() => begin('save')}>Save Current As</Button>
      </div>
      {selectingReplacement && <p role="status" className="text-sm text-muted-foreground">Select a saved workspace to replace with the current session.</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {editMode && <form aria-label="Workspace editor" className="rounded-md border p-3" onSubmit={(event) => { event.preventDefault(); void submit() }}>
        <label className="block text-sm font-medium" htmlFor="workspace-name">Workspace name</label>
        <input id="workspace-name" value={name} onChange={(event) => setName(event.target.value)} autoFocus className="mt-1 h-9 w-full rounded-md border px-2" />
        <div className="mt-3 flex gap-2">
          <Button type="submit" size="sm" disabled={!name.trim() || pending}>
            {editMode === 'rename' ? 'Save rename' : editMode === 'duplicate' ? 'Duplicate workspace' : 'Save workspace'}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => close()} disabled={pending}>Cancel</Button>
        </div>
      </form>}
      <ul className="space-y-2">
        {workspaces.map((workspace) => <li key={workspace.id} className="rounded-md border p-3">
          <p className="font-medium">{workspace.name}</p>
          <p className="text-xs text-muted-foreground">Revision {workspace.revision}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={() => void perform(() => onOpen(workspace))} disabled={pending}>Open {workspace.name}</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => begin('rename', workspace)} disabled={pending}>Rename {workspace.name}</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => begin('duplicate', workspace)} disabled={pending}>Duplicate {workspace.name}</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => { setSelectingReplacement(false); void perform(() => onReplaceWithCurrent(workspace)) }} disabled={pending}>Replace With Current</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void perform(() => onDelete(workspace))} disabled={pending}>Delete {workspace.name}</Button>
          </div>
        </li>)}
      </ul>
    </section>
  )
}
