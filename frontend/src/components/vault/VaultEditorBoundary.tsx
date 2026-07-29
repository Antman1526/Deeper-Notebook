'use client'

import {
  Component,
  type ReactNode,
} from 'react'

interface VaultEditorBoundaryProps {
  children: ReactNode
  fallback: ReactNode
  resetKey: string
}

interface VaultEditorBoundaryState {
  failed: boolean
  resetKey: string
}

export class VaultEditorBoundary extends Component<
  VaultEditorBoundaryProps,
  VaultEditorBoundaryState
> {
  state: VaultEditorBoundaryState = {
    failed: false,
    resetKey: this.props.resetKey,
  }

  static getDerivedStateFromError(): Partial<VaultEditorBoundaryState> {
    return { failed: true }
  }

  static getDerivedStateFromProps(
    props: VaultEditorBoundaryProps,
    state: VaultEditorBoundaryState,
  ): Partial<VaultEditorBoundaryState> | null {
    return props.resetKey === state.resetKey
      ? null
      : { failed: false, resetKey: props.resetKey }
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
