'use client'

import { useMemo } from 'react'
import { FileSearch, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { KnowledgePane } from '@/lib/api/knowledge-workspace'
import type { VaultMount } from '@/lib/api/vault'
import {
  useVaultGraph,
  useVaultOutgoing,
  useVaultPage,
} from '@/lib/hooks/use-vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { VaultGraph } from './VaultGraph'
import { VaultMarkdown } from './VaultMarkdown'

export type KnowledgeNavigate = (
  vaultId: string,
  noteId: string,
  relativePathHint?: string,
  titleHint?: string,
  paneId?: string,
  targetText?: string,
) => void

interface KnowledgePaneContentProps {
  pane: KnowledgePane
  mounts: VaultMount[]
  onNavigate: KnowledgeNavigate
}

function headings(markdown: string) {
  return markdown.split('\n').flatMap((line) => {
    const match = /^(#{1,3})\s+(.+)$/.exec(line)
    return match
      ? [{ level: match[1].length, text: match[2] }]
      : []
  })
}

export function KnowledgePaneContent({
  pane,
  mounts,
  onNavigate,
}: KnowledgePaneContentProps) {
  const { t } = useTranslation()
  const setTabViewMode = useKnowledgeWorkspaceStore(
    (state) => state.setTabViewMode,
  )
  const activeTab = pane.tabs.find((tab) => tab.id === pane.activeTabId)
    ?? pane.tabs[0]
  const vaultId = activeTab?.vaultId
  const noteId = activeTab?.noteId
  const page = useVaultPage(vaultId, noteId)
  const outgoing = useVaultOutgoing(vaultId, noteId)
  const visibleMode = activeTab?.viewMode === 'graph' ? 'graph' : 'reading'
  const graph = useVaultGraph(vaultId, noteId, visibleMode === 'graph')
  const markdown = page.data?.note.content
    || page.data?.note.markdown
    || page.data?.blocks
      .map((block) => block.markdown || '')
      .join('\n\n')
    || ''
  const outline = useMemo(() => headings(markdown), [markdown])
  const mount = mounts.find((candidate) => candidate.id === vaultId)
  const currentOutgoing = outgoing.data || page.data?.outgoing_links || []
  const unresolved = currentOutgoing.filter((link) => !link.resolved)

  const navigate = (targetNoteId: string) => {
    if (!activeTab) return
    const link = currentOutgoing.find(
      (candidate) => candidate.target_note_id === targetNoteId,
    )
    const graphNode = graph.data?.nodes.find(
      (candidate) => candidate.id === targetNoteId,
    )
    const titleHint = link?.target_note_title === null
      || link?.target_note_title === undefined
      ? graphNode?.title ?? undefined
      : link.target_note_title
    onNavigate(
      activeTab.vaultId,
      targetNoteId,
      link?.target_relative_path ?? undefined,
      titleHint,
      pane.id,
      link?.target_text || targetNoteId,
    )
  }

  if (!activeTab) {
    return (
      <div className="p-4 sm:p-6">
        <div className="flex min-h-72 flex-col items-center justify-center rounded-md border border-dashed p-6 text-center">
          <FileSearch className="mb-3 h-8 w-8 text-muted-foreground" />
          <h2 className="font-medium">{t('knowledge.selectNote')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('knowledge.externalReadOnly')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <Tabs
      value={visibleMode}
      onValueChange={(mode) => {
        if (mode === 'reading' || mode === 'graph') {
          setTabViewMode(pane.id, activeTab.id, mode)
        }
      }}
      className="flex min-h-full flex-col p-4 sm:p-6"
    >
      <TabsList className="w-fit">
        <TabsTrigger value="reading">{t('knowledge.reader')}</TabsTrigger>
        <TabsTrigger value="graph">{t('knowledge.localGraph')}</TabsTrigger>
      </TabsList>
      <TabsContent value="reading" className="mt-5">
        {page.isLoading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t('knowledge.noteLoading')}
          </p>
        ) : page.isError ? (
          <p role="alert" className="py-12 text-center text-sm text-destructive">
            {t('knowledge.loadError')}
          </p>
        ) : page.data ? (
          <article>
            <div className="mb-6 border-b pb-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-2xl font-semibold">
                  {page.data.note.title || activeTab.title
                    || t('knowledge.untitledNote')}
                </h2>
                <Badge variant="outline">
                  <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                  {t('knowledge.readOnly')}
                </Badge>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {mount?.name || activeTab.relativePath}
                {' · '}
                {page.data.note.source_format || mount?.format_mode || 'markdown'}
                {' · '}
                {t('knowledge.canonicalSource')}
              </p>
            </div>
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_12rem]">
              <VaultMarkdown
                vaultId={vaultId}
                markdown={markdown}
                links={currentOutgoing}
                onNavigate={navigate}
              />
              <aside className="space-y-5">
                <section>
                  <h3 className="text-sm font-semibold">
                    {t('knowledge.properties')}
                  </h3>
                  <dl className="mt-2 space-y-1 text-sm text-muted-foreground">
                    {Object.entries(page.data.note.properties || {}).length
                      ? Object.entries(page.data.note.properties || {}).map(
                        ([key, value]) => (
                          <div key={key}>
                            <dt className="font-medium text-foreground">{key}</dt>
                            <dd>{String(value)}</dd>
                          </div>
                        ),
                      )
                      : <p>{t('knowledge.noProperties')}</p>}
                  </dl>
                </section>
                <section>
                  <h3 className="text-sm font-semibold">
                    {t('knowledge.tags')}
                  </h3>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {page.data.note.tags?.length
                      ? page.data.note.tags.map((tag) => (
                        <Badge key={tag} variant="secondary">#{tag}</Badge>
                      ))
                      : (
                        <span className="text-sm text-muted-foreground">
                          {t('knowledge.noTags')}
                        </span>
                      )}
                  </div>
                </section>
                <section>
                  <h3 className="text-sm font-semibold">
                    {t('knowledge.outline')}
                  </h3>
                  <ol className="mt-2 space-y-1 text-sm text-muted-foreground">
                    {outline.map((item, index) => (
                      <li
                        key={`${item.text}-${index}`}
                        className={
                          item.level === 3
                            ? 'pl-3'
                            : item.level === 2
                              ? 'pl-1'
                              : ''
                        }
                      >
                        {item.text}
                      </li>
                    ))}
                  </ol>
                </section>
              </aside>
            </div>
          </article>
        ) : null}
      </TabsContent>
      <TabsContent value="graph" className="mt-5 min-h-0 flex-1">
        {graph.isLoading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t('knowledge.graphLoading')}
          </p>
        ) : graph.isError ? (
          <p role="alert" className="py-12 text-center text-sm text-destructive">
            {t('knowledge.graphLoadError')}
          </p>
        ) : (
          <VaultGraph
            graph={graph.data}
            unresolved={unresolved}
            onNavigate={navigate}
          />
        )}
      </TabsContent>
    </Tabs>
  )
}
