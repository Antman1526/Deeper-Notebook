import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  resetCommandSurfaceStore,
  useCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import {
  resetKnowledgeCommandContextStore,
  useKnowledgeCommandContextStore,
} from '@/lib/commands/knowledge-command-context-store'

import { KnowledgeCommandBridge } from './KnowledgeCommandBridge'

function renderBridge() {
  const workspaceRef = createRef<HTMLDivElement>()
  const fileTreeRef = createRef<HTMLDivElement>()
  const linksRef = createRef<HTMLDivElement>()
  const scanSelectedVault = vi.fn(async () => undefined)
  const openTodayOverlay = vi.fn(async () => undefined)
  const openUniqueOverlayDialog = vi.fn()
  const activePaneElement = document.createElement('section')
  document.body.append(activePaneElement)
  const result = render(
    <>
      <div ref={workspaceRef} data-testid="knowledge-workspace" tabIndex={-1}>
        <input aria-label="Knowledge input" />
        <div contentEditable data-testid="editable-content" />
      </div>
      <div ref={fileTreeRef} />
      <div ref={linksRef} />
      <KnowledgeCommandBridge
        workspaceRef={workspaceRef}
        activePaneElement={activePaneElement}
        fileTreeRef={fileTreeRef}
        linksRef={linksRef}
        selectedVaultId="vault:fixture"
        scanSelectedVault={scanSelectedVault}
        openTodayOverlay={openTodayOverlay}
        openUniqueOverlayDialog={openUniqueOverlayDialog}
      />
    </>,
  )
  return { ...result, activePaneElement, scanSelectedVault, openTodayOverlay, openUniqueOverlayDialog }
}

describe('KnowledgeCommandBridge', () => {
  beforeEach(() => {
    resetCommandSurfaceStore()
    resetKnowledgeCommandContextStore()
  })

  it('opens slash commands only from the focused Knowledge workspace', () => {
    renderBridge()
    fireEvent.keyDown(document.body, { key: '/' })
    expect(useCommandSurfaceStore.getState().kind).toBeNull()

    const workspace = screen.getByTestId('knowledge-workspace')
    workspace.focus()
    fireEvent.keyDown(workspace, { key: '/' })
    expect(useCommandSurfaceStore.getState()).toMatchObject({
      kind: 'slash',
      initialQuery: '/',
      invoker: workspace,
    })
  })

  it('requests the quick switcher for Cmd/Ctrl+O while Knowledge is mounted', () => {
    renderBridge()
    fireEvent.keyDown(document, { key: 'o', metaKey: true })
    expect(useCommandSurfaceStore.getState()).toMatchObject({
      kind: 'quick-switcher',
      initialQuery: '',
    })
  })

  it('does not intercept inputs, editable content, repeats, composition, or modified slash gestures', () => {
    renderBridge()
    const workspace = screen.getByTestId('knowledge-workspace')
    const input = screen.getByRole('textbox')
    const editable = screen.getByTestId('editable-content')
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    for (const [target, init] of [
      [input, { key: '/' }],
      [editable, { key: '/' }],
      [workspace, { key: '/', isComposing: true }],
      [workspace, { key: '/', repeat: true }],
      [workspace, { key: '/', metaKey: true }],
    ] as const) {
      fireEvent.keyDown(target, init)
    }
    expect(useCommandSurfaceStore.getState().kind).toBeNull()
  })

  it('registers selected context and clears its captured generation on unmount', () => {
    const { activePaneElement, unmount } = renderBridge()
    expect(useKnowledgeCommandContextStore.getState().context).toMatchObject({
      selectedVaultId: 'vault:fixture',
      scanSelectedVault: expect.any(Function),
      openTodayOverlay: expect.any(Function),
      openUniqueOverlayDialog: expect.any(Function),
      activePaneElement,
    })
    unmount()
    expect(useKnowledgeCommandContextStore.getState().context).toBeNull()
    activePaneElement.remove()
  })
})
