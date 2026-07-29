'use client'

import { useEffect } from 'react'

import {
  clearKnowledgeCommandContext,
  registerKnowledgeCommandContext,
} from '@/lib/commands/knowledge-command-context-store'
import { requestCommandSurface } from '@/lib/commands/command-surface-store'

export interface KnowledgeCommandBridgeProps {
  workspaceRef: React.RefObject<HTMLElement | null>
  fileTreeRef: React.RefObject<HTMLElement | null>
  linksRef: React.RefObject<HTMLElement | null>
  selectedVaultId: string | null
  scanSelectedVault: () => Promise<void>
}

function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (
    target.isContentEditable
    || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  )
}

export function KnowledgeCommandBridge({
  workspaceRef,
  fileTreeRef,
  linksRef,
  selectedVaultId,
  scanSelectedVault,
}: KnowledgeCommandBridgeProps) {
  useEffect(() => {
    const generation = registerKnowledgeCommandContext({
      selectedVaultId,
      fileTreeElement: fileTreeRef.current,
      activePaneElement: workspaceRef.current,
      linksElement: linksRef.current,
      scanSelectedVault,
    })
    return () => clearKnowledgeCommandContext(generation)
  }, [fileTreeRef, linksRef, scanSelectedVault, selectedVaultId, workspaceRef])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || event.isComposing || isEditableTarget(event.target)) return

      if (event.key.toLowerCase() === 'o' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        event.stopPropagation()
        requestCommandSurface(
          'quick-switcher',
          '',
          document.activeElement instanceof HTMLElement ? document.activeElement : null,
        )
        return
      }

      if (
        event.key === '/'
        && !event.metaKey
        && !event.ctrlKey
        && !event.altKey
        && !event.shiftKey
        && workspaceRef.current?.contains(event.target as Node)
      ) {
        event.preventDefault()
        requestCommandSurface(
          'slash',
          '/',
          document.activeElement instanceof HTMLElement ? document.activeElement : null,
        )
      }
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [workspaceRef])

  return null
}
