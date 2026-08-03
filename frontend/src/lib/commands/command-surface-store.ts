import { create } from 'zustand'

export type CommandSurfaceKind = 'global' | 'slash' | 'quick-switcher'

interface CommandSurfaceState {
  requestId: number
  kind: CommandSurfaceKind | null
  initialQuery: string
  invoker: HTMLElement | null
}

export const useCommandSurfaceStore = create<CommandSurfaceState>()(() => ({
  requestId: 0,
  kind: null,
  initialQuery: '',
  invoker: null,
}))

export function requestCommandSurface(
  kind: CommandSurfaceKind,
  initialQuery = '',
  invoker: HTMLElement | null = null,
): void {
  const requestId = useCommandSurfaceStore.getState().requestId + 1
  useCommandSurfaceStore.setState({ requestId, kind, initialQuery, invoker })
}

export function acknowledgeCommandSurface(requestId: number): void {
  useCommandSurfaceStore.setState(state => (
    state.requestId === requestId
      ? { kind: null, initialQuery: '', invoker: null }
      : state
  ))
}

export function resetCommandSurfaceStore(): void {
  useCommandSurfaceStore.setState({
    requestId: 0,
    kind: null,
    initialQuery: '',
    invoker: null,
  })
}
