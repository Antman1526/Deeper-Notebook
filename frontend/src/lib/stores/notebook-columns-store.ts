import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface NotebookColumnsState {
  sourcesCollapsed: boolean
  notesCollapsed: boolean
  // v0.8.130 — Phase 2a: the Studio column (generators, saved outputs, research runs).
  studioCollapsed: boolean
  toggleSources: () => void
  toggleNotes: () => void
  toggleStudio: () => void
  setSources: (collapsed: boolean) => void
  setNotes: (collapsed: boolean) => void
  setStudio: (collapsed: boolean) => void
}

export const useNotebookColumnsStore = create<NotebookColumnsState>()(
  persist(
    (set) => ({
      sourcesCollapsed: false,
      notesCollapsed: false,
      studioCollapsed: false,
      toggleSources: () => set((state) => ({ sourcesCollapsed: !state.sourcesCollapsed })),
      toggleNotes: () => set((state) => ({ notesCollapsed: !state.notesCollapsed })),
      toggleStudio: () => set((state) => ({ studioCollapsed: !state.studioCollapsed })),
      setSources: (collapsed) => set({ sourcesCollapsed: collapsed }),
      setNotes: (collapsed) => set({ notesCollapsed: collapsed }),
      setStudio: (collapsed) => set({ studioCollapsed: collapsed }),
    }),
    {
      name: 'notebook-columns-storage',
    }
  )
)
