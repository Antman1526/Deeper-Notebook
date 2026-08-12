'use client'

import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { AddSourceDialog } from '@/components/sources/AddSourceDialog'
import { CreateNotebookDialog } from '@/components/notebooks/CreateNotebookDialog'
import { GeneratePodcastDialog } from '@/components/podcasts/GeneratePodcastDialog'
import { QuickPodcastDialog } from '@/components/podcasts/QuickPodcastDialog'

interface SourceDialogOptions {
  defaultNotebookId?: string
  onSourceCreated?: () => void
  onSourcesCreated?: (sourceIds: readonly string[]) => void | Promise<void>
}

interface CreateDialogsContextType {
  openSourceDialog: (options?: SourceDialogOptions) => void
  openNotebookDialog: () => void
  openPodcastDialog: () => void
}

const CreateDialogsContext = createContext<CreateDialogsContextType | null>(null)

export function CreateDialogsProvider({ children }: { children: ReactNode }) {
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const [sourceDialogOptions, setSourceDialogOptions] = useState<SourceDialogOptions>({})
  const [notebookDialogOpen, setNotebookDialogOpen] = useState(false)
  const [podcastDialogOpen, setPodcastDialogOpen] = useState(false)

  const openSourceDialog = useCallback((options: SourceDialogOptions = {}) => {
    setSourceDialogOptions(options)
    setSourceDialogOpen(true)
  }, [])
  const openNotebookDialog = useCallback(() => setNotebookDialogOpen(true), [])
  const openPodcastDialog = useCallback(() => setPodcastDialogOpen(true), [])

  const handleSourceDialogOpenChange = useCallback((nextOpen: boolean) => {
    setSourceDialogOpen(nextOpen)
    if (!nextOpen) {
      setSourceDialogOptions({})
    }
  }, [])

  return (
    <CreateDialogsContext.Provider
      value={{
        openSourceDialog,
        openNotebookDialog,
        openPodcastDialog,
      }}
    >
      {children}
      <AddSourceDialog
        open={sourceDialogOpen}
        onOpenChange={handleSourceDialogOpenChange}
        defaultNotebookId={sourceDialogOptions.defaultNotebookId}
        onSourceCreated={sourceDialogOptions.onSourceCreated}
        onSourcesCreated={sourceDialogOptions.onSourcesCreated}
      />
      <CreateNotebookDialog open={notebookDialogOpen} onOpenChange={setNotebookDialogOpen} />
      <GeneratePodcastDialog open={podcastDialogOpen} onOpenChange={setPodcastDialogOpen} />
      <QuickPodcastDialog />
    </CreateDialogsContext.Provider>
  )
}

export function useCreateDialogs() {
  const context = useContext(CreateDialogsContext)
  if (!context) {
    throw new Error('useCreateDialogs must be used within a CreateDialogsProvider')
  }
  return context
}
