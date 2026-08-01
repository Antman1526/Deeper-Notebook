import { create } from 'zustand'

import {
  normalizePodcastSelections,
  podcastSelectionSchema,
  type PodcastDestination,
  type PodcastSelection,
} from '@/lib/podcasts/selection'

interface PodcastStudioState {
  isOpen: boolean
  destination: PodcastDestination | null
  selections: PodcastSelection[]
  invoker: HTMLElement | null
  open: (selections: PodcastSelection[], destination: PodcastDestination) => void
  dismiss: () => void
}

const emptyStudioState = {
  isOpen: false,
  destination: null,
  selections: [] as PodcastSelection[],
  invoker: null as HTMLElement | null,
}

/**
 * Transient review state only. It deliberately has no persistence, API call,
 * model request, or generation command; confirmation belongs to the Studio.
 */
export const usePodcastStudioStore = create<PodcastStudioState>()((set, get) => ({
  ...emptyStudioState,
  open: (selections, destination) => {
    const parsed = selections.map((selection) => podcastSelectionSchema.parse(selection))
    const activeElement = typeof document === 'undefined' ? null : document.activeElement
    set({
      isOpen: true,
      destination,
      selections: normalizePodcastSelections(parsed),
      invoker: activeElement instanceof HTMLElement ? activeElement : null,
    })
  },
  dismiss: () => {
    const invoker = get().invoker
    set(emptyStudioState)
    if (
      typeof window === 'undefined'
      || !invoker
      || !invoker.isConnected
      || invoker.hasAttribute('disabled')
    ) return
    window.setTimeout(() => {
      if (invoker.isConnected) invoker.focus()
    }, 0)
  },
}))
