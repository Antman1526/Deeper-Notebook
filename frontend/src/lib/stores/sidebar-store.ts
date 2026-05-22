import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SidebarState {
  isCollapsed: boolean
  toggleCollapse: () => void
  setCollapsed: (collapsed: boolean) => void
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      isCollapsed: false,
      toggleCollapse: () => set((state) => ({ isCollapsed: !state.isCollapsed })),
      setCollapsed: (collapsed) => set({ isCollapsed: collapsed }),
    }),
    {
      name: 'sidebar-storage',
      // v0.7.180 — Explicit partialize so only the user preference
      // (`isCollapsed`) hits localStorage. Functions aren't serializable
      // and zustand/persist drops them by default, so today this is
      // effectively a no-op — BUT it's a forward-guard. The moment a
      // future contributor adds ephemeral state to this store (e.g.
      // `isHovered`, `lastClickedAt`, a transient transition flag),
      // the default behavior would silently bleed it into localStorage
      // and across page reloads. Codifying the persistence boundary
      // here makes the intent explicit and stops that footgun cold.
      // Same pattern auth-store already uses (per lib/stores/CLAUDE.md).
      partialize: (state) => ({ isCollapsed: state.isCollapsed }),
    }
  )
)