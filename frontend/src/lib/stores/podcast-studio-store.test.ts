import { beforeEach, describe, expect, it, vi } from 'vitest'

import { usePodcastStudioStore } from './podcast-studio-store'

const selection = {
  kind: 'knowledge_document' as const,
  documentId: 'knowledge_engine_document:research',
}

describe('podcast studio store', () => {
  beforeEach(() => usePodcastStudioStore.getState().dismiss())

  it('opens an ephemeral review draft without starting production or persisting it', () => {
    const persistSpy = vi.spyOn(Storage.prototype, 'setItem')

    usePodcastStudioStore.getState().open([selection], 'quick')

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: true,
      destination: 'quick',
      selections: [selection],
    })
    expect(persistSpy).not.toHaveBeenCalled()
    persistSpy.mockRestore()
  })

  it('normalizes graph selection IDs and clears every transient value on dismiss', () => {
    usePodcastStudioStore.getState().open([{
      kind: 'graph_selection',
      documentIds: [
        'knowledge_engine_document:zeta',
        'knowledge_engine_document:alpha',
        'knowledge_engine_document:zeta',
      ],
    }], 'studio')

    expect(usePodcastStudioStore.getState().selections[0]).toMatchObject({
      documentIds: ['knowledge_engine_document:alpha', 'knowledge_engine_document:zeta'],
    })

    usePodcastStudioStore.getState().dismiss()

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: false,
      destination: null,
      selections: [],
    })
  })

  it('restores the invoking action after the review surface closes', async () => {
    const invoker = document.createElement('button')
    const dialogControl = document.createElement('button')
    document.body.append(invoker, dialogControl)

    invoker.focus()
    usePodcastStudioStore.getState().open([selection], 'quick')
    dialogControl.focus()
    usePodcastStudioStore.getState().dismiss()

    await new Promise(resolve => window.setTimeout(resolve, 0))

    expect(invoker).toHaveFocus()
    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: false,
      destination: null,
      selections: [],
    })
    invoker.remove()
    dialogControl.remove()
  })
})
