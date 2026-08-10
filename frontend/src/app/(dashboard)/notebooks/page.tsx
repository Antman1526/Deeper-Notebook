'use client'

import { useMemo, useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import { NotebookList } from './components/NotebookList'
import { Button } from '@/components/ui/button'
import { useRouter } from 'next/navigation'
import { Download, Plus, RefreshCw, Sparkles, Loader2 } from 'lucide-react'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useCreateSampleNotebook } from '@/lib/hooks/use-sample-notebook'
import { CreateNotebookDialog } from '@/components/notebooks/CreateNotebookDialog'
import { ImportNotebookDialog } from './components/ImportNotebookDialog'
import { Input } from '@/components/ui/input'
import { useTranslation } from '@/lib/hooks/use-translation'
import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'

export default function NotebooksPage() {
  const { t } = useTranslation()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  // v0.7.119 — Import dialog opens from the page header next to the
  // "New Notebook" button.
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const { data: notebooks, isLoading, refetch } = useNotebooks(false)
  const { data: archivedNotebooks } = useNotebooks(true)

  // v0.8.80 — first-run "Explore a sample notebook": seed an example notebook +
  // source, then open it.
  const router = useRouter()
  const sampleNotebook = useCreateSampleNotebook()
  const handleExploreSample = async () => {
    const id = await sampleNotebook.create()
    if (id) router.push(`/notebooks/${id}`)
  }

  const normalizedQuery = searchTerm.trim().toLowerCase()

  const filteredActive = useMemo(() => {
    if (!notebooks) {
      return undefined
    }
    if (!normalizedQuery) {
      return notebooks
    }
    return notebooks.filter((notebook) =>
      notebook.name.toLowerCase().includes(normalizedQuery)
    )
  }, [notebooks, normalizedQuery])

  const filteredArchived = useMemo(() => {
    if (!archivedNotebooks) {
      return undefined
    }
    if (!normalizedQuery) {
      return archivedNotebooks
    }
    return archivedNotebooks.filter((notebook) =>
      notebook.name.toLowerCase().includes(normalizedQuery)
    )
  }, [archivedNotebooks, normalizedQuery])

  const hasArchived = (archivedNotebooks?.length ?? 0) > 0
  const isSearching = normalizedQuery.length > 0

  return (
    <AppShell>
      <KnowledgeRouteFrame
        route="/notebooks"
        actions={
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end sm:gap-4">
            <Button
              variant="outline"
              size="sm"
              aria-label="Refresh notebooks"
              onClick={() => refetch()}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Input
              id="notebook-search"
              name="notebook-search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder={t('notebooks.searchPlaceholder')}
              autoComplete="off"
              aria-label={t('common.accessibility.searchNotebooks') || "Search notebooks"}
              className="w-full sm:w-64"
            />
            <Button variant="outline" onClick={() => setImportDialogOpen(true)}>
              <Download className="h-4 w-4 mr-2" />
              {t('notebooks.import.button')}
            </Button>
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              {t('notebooks.newNotebook')}
            </Button>
          </div>
        }
      >
        <div className="space-y-8">
          <NotebookList
            notebooks={filteredActive}
            isLoading={isLoading}
            title={t('notebooks.activeNotebooks')}
            emptyTitle={isSearching ? t('common.noMatches') : undefined}
            emptyDescription={isSearching ? t('common.tryDifferentSearch') : undefined}
            onAction={!isSearching ? () => setCreateDialogOpen(true) : undefined}
            actionLabel={!isSearching ? t('notebooks.newNotebook') : undefined}
            extraAction={
              // v0.8.80 — first-run onboarding: only when there are genuinely no
              // notebooks (not just a filtered-empty search).
              !isSearching && (notebooks?.length ?? 0) === 0 ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleExploreSample}
                  disabled={sampleNotebook.pending}
                >
                  {sampleNotebook.pending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4 mr-2" />
                  )}
                  {t('notebooks.exploreSample', { defaultValue: 'Explore a sample notebook' })}
                </Button>
              ) : undefined
            }
          />

          {hasArchived && (
            <NotebookList
              notebooks={filteredArchived}
              isLoading={false}
              title={t('notebooks.archivedNotebooks')}
              collapsible
              emptyTitle={isSearching ? t('common.noMatches') : undefined}
              emptyDescription={isSearching ? t('common.tryDifferentSearch') : undefined}
            />
          )}
        </div>
      </KnowledgeRouteFrame>

      <CreateNotebookDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
      <ImportNotebookDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
      />
    </AppShell>
  )
}
