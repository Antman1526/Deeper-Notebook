'use client'

import { useEffect, useMemo, useState } from 'react'
import { FileSearch, RefreshCw, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useScanVault, useVaultBacklinks, useVaultFiles, useVaultGraph, useVaultOutgoing, useVaultPage, useVaults } from '@/lib/hooks/use-vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import { VaultFileTree } from './VaultFileTree'
import { VaultGraph } from './VaultGraph'
import { VaultLinks } from './VaultLinks'
import { VaultMarkdown } from './VaultMarkdown'

function headings(markdown: string) { return markdown.split('\n').flatMap((line) => { const match = /^(#{1,3})\s+(.+)$/.exec(line); return match ? [{ level: match[1].length, text: match[2] }] : [] }) }

export function KnowledgeExplorer() {
  const { t } = useTranslation()
  const mounts = useVaults()
  const [vaultId, setVaultId] = useState('')
  const [noteId, setNoteId] = useState('')
  const [tab, setTab] = useState('reader')
  useEffect(() => { if (!vaultId && mounts.data?.[0]) setVaultId(mounts.data[0].id) }, [mounts.data, vaultId])
  const files = useVaultFiles(vaultId)
  const page = useVaultPage(vaultId, noteId)
  const backlinks = useVaultBacklinks(vaultId, noteId)
  const outgoing = useVaultOutgoing(vaultId, noteId)
  const graph = useVaultGraph(vaultId, noteId, tab === 'graph')
  const scan = useScanVault(vaultId, noteId)
  const markdown = page.data?.note.content || page.data?.note.markdown || page.data?.blocks.map((block) => block.markdown || '').join('\n\n') || ''
  const outline = useMemo(() => headings(markdown), [markdown])
  const selectVault = (id: string) => { setVaultId(id); setNoteId(''); setTab('reader') }
  const navigate = (id: string) => { setNoteId(id); setTab('reader') }
  const selected = mounts.data?.find((mount) => mount.id === vaultId)
  const unresolved = (outgoing.data || page.data?.outgoing_links || []).filter((link) => !link.resolved)
  const linksLoading = Boolean(noteId && (backlinks.isLoading || outgoing.isLoading))
  const linksError = Boolean(noteId && (backlinks.isError || outgoing.isError))

  return <div className="flex min-h-0 flex-1 flex-col">
    <header className="border-b px-4 py-4 sm:px-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-xl font-semibold">{t('navigation.knowledge')}</h1><p className="mt-1 text-sm text-muted-foreground">{t('knowledge.description')}</p></div><Button type="button" variant="outline" onClick={() => void scan.mutateAsync()} disabled={!vaultId || scan.isPending}><RefreshCw className={`mr-2 h-4 w-4 ${scan.isPending ? 'animate-spin' : ''}`} />{t('knowledge.scan')}</Button></div></header>
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)_minmax(15rem,20rem)]">
      <aside className="flex min-h-64 flex-col gap-4 border-b p-4 lg:border-b-0 lg:border-r" aria-label={t('knowledge.files')}><label className="text-sm font-medium" htmlFor="vault-mount">{t('knowledge.mounts')}</label><select id="vault-mount" value={vaultId} onChange={(event) => selectVault(event.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" disabled={mounts.isLoading || mounts.isError}>{mounts.data?.map((mount) => <option key={mount.id} value={mount.id}>{mount.name} · {mount.format_mode}</option>)}</select>{mounts.isLoading ? <p className="text-sm text-muted-foreground">{t('knowledge.mountsLoading')}</p> : mounts.isError ? <p role="alert" className="text-sm text-destructive">{t('knowledge.loadError')}</p> : !mounts.data?.length ? <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">{t('knowledge.noMounts')}</p> : <><div className="rounded-md bg-muted p-3 text-sm"><span className="font-medium">{t('knowledge.status')}</span><p className="mt-1 text-muted-foreground">{selected?.state || t('common.unknown')}</p></div>{files.isLoading ? <p className="text-sm text-muted-foreground">{t('knowledge.filesLoading')}</p> : files.isError ? <p role="alert" className="text-sm text-destructive">{t('knowledge.loadError')}</p> : <VaultFileTree files={files.data || []} selectedNoteId={noteId} onSelect={navigate} />}</>}</aside>
      <main className="min-w-0 overflow-y-auto p-4 sm:p-6"><Tabs value={tab} onValueChange={setTab} className="min-h-full"><TabsList><TabsTrigger value="reader">{t('knowledge.reader')}</TabsTrigger><TabsTrigger value="graph" disabled={!noteId}>{t('knowledge.localGraph')}</TabsTrigger></TabsList><TabsContent value="reader" className="mt-5">{!noteId ? <div className="flex min-h-72 flex-col items-center justify-center rounded-md border border-dashed p-6 text-center"><FileSearch className="mb-3 h-8 w-8 text-muted-foreground" /><h2 className="font-medium">{t('knowledge.selectNote')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('knowledge.externalReadOnly')}</p></div> : page.isLoading ? <p className="py-12 text-center text-sm text-muted-foreground">{t('knowledge.noteLoading')}</p> : page.isError ? <p role="alert" className="py-12 text-center text-sm text-destructive">{t('knowledge.loadError')}</p> : page.data ? <article><div className="mb-6 border-b pb-4"><div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold">{page.data.note.title || t('knowledge.untitledNote')}</h2><Badge variant="outline"><ShieldCheck className="mr-1 h-3.5 w-3.5" />{t('knowledge.readOnly')}</Badge></div><p className="mt-2 text-sm text-muted-foreground">{selected?.name} · {page.data.note.source_format || selected?.format_mode || 'markdown'} · {t('knowledge.canonicalSource')}</p></div><div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_12rem]"><VaultMarkdown markdown={markdown} links={page.data.outgoing_links} onNavigate={navigate} /><aside className="space-y-5"><section><h3 className="text-sm font-semibold">{t('knowledge.properties')}</h3><dl className="mt-2 space-y-1 text-sm text-muted-foreground">{Object.entries(page.data.note.properties || {}).length ? Object.entries(page.data.note.properties || {}).map(([key, value]) => <div key={key}><dt className="font-medium text-foreground">{key}</dt><dd>{String(value)}</dd></div>) : <p>{t('knowledge.noProperties')}</p>}</dl></section><section><h3 className="text-sm font-semibold">{t('knowledge.tags')}</h3><div className="mt-2 flex flex-wrap gap-1">{page.data.note.tags?.length ? page.data.note.tags.map((tag) => <Badge key={tag} variant="secondary">#{tag}</Badge>) : <span className="text-sm text-muted-foreground">{t('knowledge.noTags')}</span>}</div></section><section><h3 className="text-sm font-semibold">{t('knowledge.outline')}</h3><ol className="mt-2 space-y-1 text-sm text-muted-foreground">{outline.map((item, index) => <li key={`${item.text}-${index}`} className={item.level === 3 ? 'pl-3' : item.level === 2 ? 'pl-1' : ''}>{item.text}</li>)}</ol></section></aside></div></article> : null}</TabsContent><TabsContent value="graph" className="mt-5">{graph.isLoading ? <p className="py-12 text-center text-sm text-muted-foreground">{t('knowledge.graphLoading')}</p> : graph.isError ? <p role="alert" className="py-12 text-center text-sm text-destructive">{t('knowledge.graphLoadError')}</p> : <VaultGraph graph={graph.data} unresolved={unresolved} onNavigate={navigate} />}</TabsContent></Tabs></main>
      <aside className="space-y-6 border-t p-4 lg:border-l lg:border-t-0" aria-label={t('knowledge.noteLinks')}>{linksLoading ? <p className="text-sm text-muted-foreground">{t('knowledge.linksLoading')}</p> : linksError ? <p role="alert" className="text-sm text-destructive">{t('knowledge.linksLoadError')}</p> : <><VaultLinks title={t('knowledge.backlinks')} links={backlinks.data || page.data?.backlinks || []} direction="source" unresolvedLabel={t('knowledge.unresolved')} onNavigate={navigate} /><VaultLinks title={t('knowledge.outgoing')} links={outgoing.data || page.data?.outgoing_links || []} direction="target" unresolvedLabel={t('knowledge.unresolved')} onNavigate={navigate} /></>}</aside>
    </div>
  </div>
}
