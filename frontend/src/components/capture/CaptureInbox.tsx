'use client'

import { useState } from 'react'
import { FolderPlus, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCaptureActions, useCaptureItems, useCaptureRoots } from '@/lib/hooks/use-capture'
import { isSourceVisualsEnabled, isVisualSystemV2Enabled } from '@/lib/features'
import { CaptureItemRow } from './CaptureItemRow'

export function CaptureInbox() {
  const roots = useCaptureRoots()
  const items = useCaptureItems()
  const actions = useCaptureActions()
  const showVisualCover = isVisualSystemV2Enabled() && isSourceVisualsEnabled()
  const [path, setPath] = useState('')
  const addRoot = async () => { await actions.addRoot.mutateAsync(path.trim()); setPath('') }
  const scan = () => void actions.scan.mutateAsync(undefined)
  return <div className="space-y-5"><section className="border-b pb-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-base font-semibold">Approved folders</h2><p className="mt-1 text-sm text-muted-foreground">Only folders you add here are scanned. Originals remain in place.</p></div><Button type="button" variant="outline" onClick={scan} disabled={actions.scan.isPending}><RefreshCw className={`mr-2 h-4 w-4 ${actions.scan.isPending ? 'animate-spin' : ''}`} />Scan now</Button></div><ul className="mt-3 space-y-1 text-sm text-muted-foreground">{roots.data?.map((root) => <li key={root.path} className="truncate">{root.path}</li>)}</ul><div className="mt-3 flex gap-2"><Input aria-label="Capture folder path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="Add a local or Google Drive Desktop folder" /><Button type="button" variant="outline" disabled={!path.trim() || actions.addRoot.isPending} onClick={() => void addRoot()}><FolderPlus className="mr-2 h-4 w-4" />Add</Button></div></section><section><div className="flex items-center justify-between gap-3"><h2 className="text-base font-semibold">Inbox</h2><span className="text-sm text-muted-foreground">{items.data?.length ?? 0} items</span></div>{items.isLoading ? <p className="mt-4 text-sm text-muted-foreground">Loading local intake…</p> : items.isError ? <p role="alert" className="mt-4 text-sm text-destructive">The capture inbox could not be loaded.</p> : items.data?.length ? <div className="mt-3">{items.data.map((item) => <CaptureItemRow key={item.id ?? `${item.root_path}:${item.relative_path}`} item={item} showVisualCover={showVisualCover} />)}</div> : <p className="mt-4 rounded-md border border-dashed p-5 text-sm text-muted-foreground">No supported files are ready yet. Add a folder and scan after copying a document, audio file, or video into it.</p>}</section></div>
}
