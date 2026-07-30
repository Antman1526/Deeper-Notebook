import { useRef, useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgePane } from '@/lib/api/knowledge-workspace'
import { getKnowledgeTabId, KnowledgeTabStrip } from './KnowledgeTabStrip'

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
      sourceAuthority: 'external-vault',
    },
    {
      id: 'tab-2',
      vaultId: 'vault:one',
      noteId: 'note:research',
      title: 'Research',
      relativePath: 'Projects/Research.md',
      viewMode: 'reading',
      sourceAuthority: 'external-vault',
    },
    {
      id: 'tab-3',
      vaultId: 'vault:one',
      noteId: 'note:decisions',
      title: 'Decisions',
      relativePath: 'Projects/Decisions.md',
      viewMode: 'graph',
      sourceAuthority: 'external-vault',
    },
  ],
}

function renderTabStrip() {
  const onActivateTab = vi.fn()
  const onCloseTab = vi.fn()
  render(
    <KnowledgeTabStrip
      pane={pane}
      panelId="knowledge-panel-pane-1"
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

  it('associates every stable tab ID with its pane content panel', () => {
    renderTabStrip()

    expect(screen.getByRole('tab', { name: 'Plan' })).toHaveAttribute(
      'id',
      'knowledge-tab-6:pane-1-5:tab-1',
    )
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveAttribute('aria-controls', 'knowledge-panel-pane-1')
    }
  })

  it('keeps DOM tab IDs distinct when pane and tab delimiters are ambiguous', () => {
    expect(getKnowledgeTabId('pane-a-b', 'tab-c')).not.toBe(
      getKnowledgeTabId('pane-a', 'b-tab-c'),
    )
  })

  it('moves focus from a closed active tab to the newly active adjacent tab', () => {
    function StatefulTabStripHarness() {
      const [currentPane, setCurrentPane] = useState(pane)

      return (
        <KnowledgeTabStrip
          pane={currentPane}
          panelId="knowledge-panel-pane-1"
          onActivateTab={(_paneId, tabId) => {
            setCurrentPane((current) => ({ ...current, activeTabId: tabId }))
          }}
          onCloseTab={(_paneId, tabId) => {
            setCurrentPane((current) => {
              const closedIndex = current.tabs.findIndex((tab) => tab.id === tabId)
              const tabs = current.tabs.filter((tab) => tab.id !== tabId)
              return {
                ...current,
                tabs,
                activeTabId: current.activeTabId === tabId
                  ? tabs[closedIndex]?.id ?? tabs[closedIndex - 1]?.id ?? null
                  : current.activeTabId,
              }
            })
          }}
        />
      )
    }

    render(<StatefulTabStripHarness />)
    const closeActiveTab = screen.getByRole('button', {
      name: 'Close Research',
    })
    closeActiveTab.focus()

    fireEvent.click(closeActiveTab)

    expect(screen.queryByRole('tab', { name: 'Research' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Decisions' })).toHaveFocus()
  })

  it('requests focus on the pane fallback after its final tab closes', () => {
    function SingletonTabHarness() {
      const fallbackRef = useRef<HTMLDivElement>(null)
      const [currentPane, setCurrentPane] = useState<KnowledgePane>({
        ...pane,
        activeTabId: 'tab-1',
        tabs: [pane.tabs[0]],
      })

      return (
        <>
          <KnowledgeTabStrip
            pane={currentPane}
            panelId="knowledge-panel-pane-1"
            onActivateTab={() => undefined}
            onCloseTab={() => {
              setCurrentPane((current) => ({
                ...current,
                activeTabId: null,
                tabs: [],
              }))
            }}
            onRequestFocusFallback={() => fallbackRef.current?.focus()}
          />
          <div
            ref={fallbackRef}
            id="knowledge-panel-pane-1"
            role="tabpanel"
            aria-label="Empty pane"
            tabIndex={0}
          />
        </>
      )
    }

    render(<SingletonTabHarness />)
    const closeFinalTab = screen.getByRole('button', { name: 'Close Plan' })
    const fallbackPanel = screen.getByRole('tabpanel', { name: 'Empty pane' })
    closeFinalTab.focus()

    fireEvent.click(closeFinalTab)

    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(fallbackPanel).toHaveFocus()
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
