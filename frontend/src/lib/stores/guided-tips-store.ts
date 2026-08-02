import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface TipIdentity {
  id: string
  version: number
}

interface GuidedTipsState {
  enabled: boolean
  completed: Record<string, number>
  setEnabled: (enabled: boolean) => void
  complete: (tip: TipIdentity) => void
  replayAll: () => void
  isComplete: (tip: TipIdentity) => boolean
}

export const useGuidedTipsStore = create<GuidedTipsState>()(
  persist(
    (set, get) => ({
      enabled: true,
      completed: {},
      setEnabled: (enabled) => set({ enabled }),
      complete: (tip) => set((state) => ({
        completed: {
          ...state.completed,
          [tip.id]: Math.max(state.completed[tip.id] ?? 0, tip.version),
        },
      })),
      replayAll: () => set({ completed: {} }),
      isComplete: (tip) => (get().completed[tip.id] ?? 0) >= tip.version,
    }),
    {
      name: 'dn-guided-tips-v1',
      partialize: (state) => ({ enabled: state.enabled, completed: state.completed }),
    },
  ),
)
