import { describe, expect, it, vi } from 'vitest'

import {
  availableKnowledgeCommands,
  executeKnowledgeCommand,
  knowledgeCommandDefinitions,
  type CommandDefinition,
  type KnowledgeCommandExecutionContext,
} from './command-registry'

function context(): KnowledgeCommandExecutionContext {
  return {
    activePaneId: 'pane-1',
    activeTabId: 'tab-1',
    paneCount: 2,
    selectedVaultId: 'vault:one',
    setViewMode: vi.fn(),
    splitPane: vi.fn(),
    closePane: vi.fn(),
    closeTab: vi.fn(),
    scanSelectedVault: vi.fn(async () => undefined),
    focusFileTree: vi.fn(),
    focusActivePane: vi.fn(),
    focusLinks: vi.fn(),
    moveTab: vi.fn(),
  }
}

describe('knowledge command registry', () => {
  it('exposes only read and workspace commands in slash mode', () => {
    const commands = availableKnowledgeCommands(context(), 'slash')
    expect(commands.length).toBeGreaterThan(0)
    expect(commands.every(command => command.safety !== 'external-write')).toBe(true)
  })

  it('disables close-pane with one pane and executes view changes exactly once', async () => {
    const singlePane = { ...context(), paneCount: 1 }
    expect(availableKnowledgeCommands(singlePane, 'global')
      .find(command => command.id === 'knowledge.close-pane')?.available).toBe(false)
    await expect(executeKnowledgeCommand(
      'knowledge.close-pane',
      singlePane,
    )).resolves.toBe(false)
    await expect(executeKnowledgeCommand(
      'knowledge.view-source',
      singlePane,
    )).resolves.toBe(true)
    expect(singlePane.setViewMode).toHaveBeenCalledWith('source')
    expect(singlePane.setViewMode).toHaveBeenCalledTimes(1)
  })

  it('makes callback-backed scan and focus commands unavailable without callbacks', () => {
    const commands = availableKnowledgeCommands({
      ...context(),
      scanSelectedVault: null,
      focusFileTree: null,
      focusActivePane: null,
      focusLinks: null,
    }, 'global')

    expect(commands.find(command => command.id === 'knowledge.scan-vault')?.available).toBe(false)
    expect(commands.find(command => command.id === 'knowledge.focus-files')?.available).toBe(false)
    expect(commands.find(command => command.id === 'knowledge.focus-pane')?.available).toBe(false)
    expect(commands.find(command => command.id === 'knowledge.focus-links')?.available).toBe(false)
  })

  it('declares the complete safe command set and rejects unknown commands', async () => {
    expect(knowledgeCommandDefinitions).toHaveLength(14)
    expect(knowledgeCommandDefinitions.every(command => (
      command.safety === 'read' || command.safety === 'workspace'
    ))).toBe(true)
    await expect(executeKnowledgeCommand('knowledge.unknown' as never, context()))
      .resolves.toBe(false)
  })

  it('does not execute an external-write command if one is registered in future', async () => {
    const execute = vi.fn()
    const externalWrite = {
      id: 'knowledge.future-external-write',
      scope: 'knowledge',
      safety: 'external-write',
      labelKey: 'knowledge.commands.futureExternalWrite',
      aliases: [],
      keywords: [],
      isAvailable: () => true,
      execute,
    } as unknown as CommandDefinition
    knowledgeCommandDefinitions.push(externalWrite)

    try {
      await expect(executeKnowledgeCommand(externalWrite.id, context())).resolves.toBe(false)
      expect(execute).not.toHaveBeenCalled()
    } finally {
      knowledgeCommandDefinitions.pop()
    }
  })
})
