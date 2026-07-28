import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgePane } from '@/lib/api/knowledge-workspace'
import { KnowledgeTabStrip } from './KnowledgeTabStrip'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { title?: string }) => {
      if (key === 'knowledge.openTabs') return 'Open tabs'
      if (key === 'knowledge.closeTab') return `Close ${options?.title ?? ''}`.trim()
      return key
    },
  }),
}))

const pane: KnowledgePane = {
  id: 'pane-1',
  activeTabId: 'tab-2',
  tabs: [
    {
      id: 'tab-1',
      vaultId: 'vault:one',
      noteId: 'note:plan',
      title: 'Plan',
      relativePath: 'Projects/Plan.md',
      viewMode: 'reading',
    },
    {
      id: 'tab-2',
      vaultId: 'vault:one',
      noteId: 'note:research',
      title: 'Research',
      relativePath: 'Projects/Research.md',
      viewMode: 'reading',
    },
    {
      id: 'tab-3',
      vaultId: 'vault:one',
      noteId: 'note:decisions',
      title: 'Decisions',
      relativePath: 'Projects/Decisions.md',
      viewMode: 'graph',
    },
  ],
}

function renderTabStrip() {
  const onActivateTab = vi.fn()
  const onCloseTab = vi.fn()
  render(
    <KnowledgeTabStrip
      pane={pane}
      onActivateTab={onActivateTab}
      onCloseTab={onCloseTab}
    />,
  )
  return { onActivateTab, onCloseTab }
}

describe('KnowledgeTabStrip', () => {
  it('exposes the active tab through selection and roving tab order', () => {
    renderTabStrip()

    expect(screen.getByRole('tablist', { name: 'Open tabs' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Research' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByRole('tab', { name: 'Research' })).toHaveAttribute(
      'tabindex',
      '0',
    )
    expect(screen.getByRole('tab', { name: 'Plan' })).toHaveAttribute(
      'tabindex',
      '-1',
    )
  })

  it('activates a clicked tab without conflating its adjacent close control', () => {
    const { onActivateTab, onCloseTab } = renderTabStrip()

    fireEvent.click(screen.getByRole('tab', { name: 'Plan' }))
    expect(onActivateTab).toHaveBeenCalledWith('pane-1', 'tab-1')
    expect(onCloseTab).not.toHaveBeenCalled()

    onActivateTab.mockClear()
    fireEvent.click(screen.getByRole('button', { name: 'Close Plan' }))
    expect(onCloseTab).toHaveBeenCalledWith('pane-1', 'tab-1')
    expect(onActivateTab).not.toHaveBeenCalled()
  })

  it.each([
    { start: 'Decisions', key: 'ArrowRight', target: 'Plan' },
    { start: 'Plan', key: 'ArrowLeft', target: 'Decisions' },
    { start: 'Research', key: 'Home', target: 'Plan' },
    { start: 'Research', key: 'End', target: 'Decisions' },
  ])('moves focus and selection from $start to $target with $key', ({
    start,
    key,
    target,
  }) => {
    const { onActivateTab } = renderTabStrip()
    const startingTab = screen.getByRole('tab', { name: start })
    const targetTab = screen.getByRole('tab', { name: target })

    startingTab.focus()
    fireEvent.keyDown(startingTab, { key })

    expect(targetTab).toHaveFocus()
    expect(onActivateTab).toHaveBeenCalledWith(
      'pane-1',
      pane.tabs.find((tab) => tab.title === target)?.id,
    )
  })
})
