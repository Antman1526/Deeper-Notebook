import { create } from 'zustand'

import type { ResearchMode } from '@/lib/knowledge/research-modes'

export interface KnowledgeCommandPageContext {
  selectedVaultId: string | null
  fileTreeElement?: HTMLElement | null
  activePaneElement?: HTMLElement | null
  linksElement?: HTMLElement | null
  scanSelectedVault?: () => Promise<void>
  openTodayOverlay?: () => Promise<void>
  openUniqueOverlayDialog?: () => void
  bookmarkCurrentTarget?: () => void | Promise<void>
  openBookmarks?: () => void
  randomNote?: () => void | Promise<void>
  openWorkspaces?: () => void
  saveWorkspaceAs?: () => void
  replaceWorkspace?: () => void
  toggleMetrics?: () => void
  researchModeAvailability?: Record<ResearchMode, { available: boolean; reason: string | null }>
  openResearchMode?: (mode: ResearchMode) => void
}

interface KnowledgeCommandContextState {
  generation: number
  context: KnowledgeCommandPageContext | null
}

export const useKnowledgeCommandContextStore =
  create<KnowledgeCommandContextState>()(() => ({
    generation: 0,
    context: null,
  }))

export function registerKnowledgeCommandContext(
  context: KnowledgeCommandPageContext,
): number {
  const generation = useKnowledgeCommandContextStore.getState().generation + 1
  useKnowledgeCommandContextStore.setState({ generation, context })
  return generation
}

export function clearKnowledgeCommandContext(generation: number): void {
  if (useKnowledgeCommandContextStore.getState().generation !== generation) return
  useKnowledgeCommandContextStore.setState({ context: null })
}

export function resetKnowledgeCommandContextStore(): void {
  useKnowledgeCommandContextStore.setState({ context: null })
}
