import { create } from 'zustand'

import type { OverlayPage } from '@/lib/api/overlay'

export interface OverlayDraftSnapshot {
  noteId: string
  loadedPage: OverlayPage
  title: string
  markdown: string
}

interface OverlayDraftState {
  drafts: Record<string, OverlayDraftSnapshot>
  saveDraft: (viewId: string, snapshot: OverlayDraftSnapshot) => void
  clearDraft: (viewId: string) => void
}

const MAX_DRAFTS = 128

export const useOverlayDraftStore = create<OverlayDraftState>()((set) => ({
  drafts: {},
  saveDraft: (viewId, snapshot) => {
    if (!viewId || snapshot.noteId !== snapshot.loadedPage.overlay.id) return
    set((state) => {
      const drafts = { ...state.drafts }
      if (!(viewId in drafts) && Object.keys(drafts).length >= MAX_DRAFTS) {
        delete drafts[Object.keys(drafts)[0]]
      }
      drafts[viewId] = snapshot
      return { drafts }
    })
  },
  clearDraft: (viewId) => {
    set((state) => {
      if (!(viewId in state.drafts)) return state
      const drafts = { ...state.drafts }
      delete drafts[viewId]
      return { drafts }
    })
  },
}))

export function clearOverlayDraft(viewId: string): void {
  useOverlayDraftStore.getState().clearDraft(viewId)
}

export function clearOverlayDrafts(viewIds: Iterable<string>): void {
  const state = useOverlayDraftStore.getState()
  for (const viewId of viewIds) state.clearDraft(viewId)
}

export function resetOverlayDraftStore(): void {
  useOverlayDraftStore.setState({ drafts: {} })
}
