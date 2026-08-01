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
  open: (selections: PodcastSelection[], destination: PodcastDestination) => void
  dismiss: () => void
}

const emptyStudioState = {
  isOpen: false,
  destination: null,
  selections: [] as PodcastSelection[],
}

/**
 * Transient review state only. It deliberately has no persistence, API call,
 * model request, or generation command; confirmation belongs to the Studio.
 */
export const usePodcastStudioStore = create<PodcastStudioState>()((set) => ({
  ...emptyStudioState,
  open: (selections, destination) => {
    const parsed = selections.map((selection) => podcastSelectionSchema.parse(selection))
    set({ isOpen: true, destination, selections: normalizePodcastSelections(parsed) })
  },
  dismiss: () => set(emptyStudioState),
}))
