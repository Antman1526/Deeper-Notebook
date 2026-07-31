'use client'

import { useCallback, useMemo, useRef } from 'react'
import { EditorView } from '@codemirror/view'

import type { KnowledgeViewMode } from '@/lib/api/knowledge-workspace'
import type { VaultLink, VaultPage } from '@/lib/api/vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  buildMarkdownModel,
  type HeadingDescriptor,
} from '@/lib/vault/markdown-model'

import { VaultEditorBoundary } from './VaultEditorBoundary'
import { VaultLivePreview } from './VaultLivePreview'
import { VaultMarkdown } from './VaultMarkdown'
import { VaultNoteSidebar } from './VaultNoteSidebar'
import { VaultSourceView } from './VaultSourceView'

type DocumentViewMode = Exclude<KnowledgeViewMode, 'graph'>

interface VaultDocumentViewProps {
  viewId: string
  mode: DocumentViewMode
  page: VaultPage
  onNavigate: (noteId: string) => void
  onPreview?: (link: VaultLink) => void
}

function encodeIdPrefix(value: string): string {
  const encoded = Array.from({ length: value.length }, (_, index) => (
    value.charCodeAt(index).toString(16).padStart(4, '0')
  )).join('')
  return `v-${encoded || 'empty'}`
}

function normalizedEditorOffset(source: string, rawOffset: number): number {
  return source
    .slice(0, Math.max(0, Math.min(rawOffset, source.length)))
    .replace(/\r\n?/g, '\n')
    .length
}

export function VaultDocumentView({
  viewId,
  mode,
  page,
  onNavigate,
  onPreview,
}: VaultDocumentViewProps) {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLElement>(null)
  const markdown = page.note.content ?? page.note.markdown ?? ''
  const parserMarkdown = useMemo(
    () => markdown.replace(/\r(?!\n)/g, '\n'),
    [markdown],
  )
  const model = useMemo(
    () => buildMarkdownModel(parserMarkdown),
    [parserMarkdown],
  )
  const headingIdPrefix = useMemo(() => encodeIdPrefix(viewId), [viewId])
  const title = page.note.title?.trim()
    || page.file.relative_path.split('/').at(-1)?.replace(/\.md$/i, '')
    || t('knowledge.untitledNote')
  const readableBlock = page.blocks.find((block) => block.knowledge_block_id)
  const reading = (
    <section aria-label={`${title} reading view`} data-knowledge-block-id={readableBlock?.knowledge_block_id ?? undefined} data-source-revision-id={readableBlock?.source_revision_id ?? undefined}>
      <VaultMarkdown
        vaultId={page.file.vault_id}
        noteId={page.note.id}
        headingIdPrefix={headingIdPrefix}
        markdown={parserMarkdown}
        links={page.outgoing_links}
        onNavigate={onNavigate}
        onPreview={onPreview}
        footnoteLabel={t('knowledge.footnotes')}
      />
    </section>
  )

  const onHeading = useCallback((heading: HeadingDescriptor) => {
    const container = containerRef.current
    if (!container) return
    if (mode === 'reading') {
      const target = Array.from(
        container.querySelectorAll<HTMLElement>('[data-heading-slug]'),
      ).find(
        (candidate) => candidate.dataset.headingSlug === heading.slug,
      )
      target?.scrollIntoView({ block: 'start' })
      return
    }

    const editor = container.querySelector<HTMLElement>('[role="textbox"]')
    if (!editor) return
    const view = EditorView.findFromDOM(editor)
    if (!view) return
    const offset = normalizedEditorOffset(markdown, heading.sourceFrom)
    view.dispatch({
      selection: { anchor: offset },
      effects: EditorView.scrollIntoView(offset, { y: 'center' }),
    })
  }, [markdown, mode])

  const accessibleMode = mode === 'reading'
    ? t('knowledge.reader')
    : mode === 'source'
      ? t('knowledge.source')
      : t('knowledge.livePreview')
  const modeLabel = mode === 'reading'
    ? `${title} reading view`
    : mode === 'source'
      ? `${title} source`
      : `${title} live preview`
  const resetKey = `${page.note.id}:${mode}:${page.file.content_hash}`
  const document = markdown.length === 0 ? (
    <section
      aria-label={modeLabel}
      className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground"
    >
      {t('knowledge.emptyNote')}
    </section>
  ) : mode === 'reading' ? reading
    : (
      <VaultEditorBoundary resetKey={resetKey} fallback={reading}>
        {mode === 'source' ? (
          <VaultSourceView
            title={title}
            markdown={markdown}
            file={page.file}
          />
        ) : (
          <VaultLivePreview
            title={title}
            markdown={markdown}
            links={page.outgoing_links}
            onNavigate={onNavigate}
          />
        )}
      </VaultEditorBoundary>
    )

  return (
    <article
      ref={containerRef}
      className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_12rem]"
    >
      <div className="min-w-0">
        <p className="sr-only">
          {t('knowledge.readOnlyMode', { mode: accessibleMode })}
        </p>
        {document}
      </div>
      <VaultNoteSidebar model={model} page={page} onHeading={onHeading} />
    </article>
  )
}
