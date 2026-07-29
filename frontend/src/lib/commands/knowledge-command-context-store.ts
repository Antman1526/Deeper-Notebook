import { create } from 'zustand'

export interface KnowledgeCommandPageContext {
  selectedVaultId: string | null
  fileTreeElement?: HTMLElement | null
  activePaneElement?: HTMLElement | null
  linksElement?: HTMLElement | null
  scanSelectedVault?: () => Promise<void>
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
