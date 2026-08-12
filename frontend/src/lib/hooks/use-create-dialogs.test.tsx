import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CreateDialogsProvider, useCreateDialogs } from './use-create-dialogs'

const emittedSourceIds = ['source:one'] as const

vi.unmock('@/lib/hooks/use-create-dialogs')

vi.mock('@/components/sources/AddSourceDialog', () => ({
  AddSourceDialog: ({
    onSourceCreated,
    onSourcesCreated,
  }: {
    onSourceCreated?: () => void
    onSourcesCreated?: (sourceIds: readonly string[]) => void | Promise<void>
  }) => (
    <button
      type="button"
      onClick={() => {
        onSourceCreated?.()
        void onSourcesCreated?.(emittedSourceIds)
      }}
    >
      Emit source
    </button>
  ),
}))
vi.mock('@/components/notebooks/CreateNotebookDialog', () => ({ CreateNotebookDialog: () => null }))
vi.mock('@/components/podcasts/GeneratePodcastDialog', () => ({ GeneratePodcastDialog: () => null }))
vi.mock('@/components/podcasts/QuickPodcastDialog', () => ({ QuickPodcastDialog: () => null }))

function Harness({ onLegacy, onBatch }: {
  onLegacy: () => void
  onBatch: (sourceIds: readonly string[]) => void
}) {
  const { openSourceDialog } = useCreateDialogs()
  return (
    <>
      <button
        type="button"
        onClick={() => openSourceDialog({ onSourceCreated: onLegacy, onSourcesCreated: onBatch })}
      >
        Open source dialog
      </button>
    </>
  )
}

describe('CreateDialogsProvider source callbacks', () => {
  it('forwards bounded batch IDs while preserving the legacy once callback', () => {
    const onLegacy = vi.fn()
    const onBatch = vi.fn()
    render(
      <CreateDialogsProvider>
        <Harness onLegacy={onLegacy} onBatch={onBatch} />
      </CreateDialogsProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Open source dialog' }))
    fireEvent.click(screen.getByRole('button', { name: 'Emit source' }))

    expect(onLegacy).toHaveBeenCalledOnce()
    expect(onLegacy).toHaveBeenCalledWith()
    expect(onBatch).toHaveBeenCalledOnce()
    expect(onBatch).toHaveBeenCalledWith(emittedSourceIds)
  })
})
