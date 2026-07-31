import type { ReactNode } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/ui/resizable', () => ({
  ResizablePanelGroup: ({
    children,
    direction,
    onLayout,
  }: {
    children: ReactNode
    direction: 'horizontal' | 'vertical'
    onLayout?: (sizes: number[]) => void
  }) => (
    <div data-direction={direction}>
      <button type="button" onClick={() => onLayout?.([35, 65])}>Report layout</button>
      {children}
    </div>
  ),
  ResizablePanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizableHandle: ({ 'aria-label': ariaLabel }: { 'aria-label': string }) => (
    <div role="separator" aria-label={ariaLabel} />
  ),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'knowledge.openTabs': 'Open tabs',
      'knowledge.knowledgeWorkspace': 'Knowledge workspace',
      'knowledge.knowledgePane': 'Knowledge pane',
      'knowledge.splitPaneRight': 'Split pane right',
      'knowledge.splitPaneDown': 'Split pane down',
      'knowledge.closePane': 'Close pane',
      'knowledge.resizeHorizontalSplit': 'Resize horizontal split',
      'knowledge.resizeVerticalSplit': 'Resize vertical split',
    }[key] ?? key),
  }),
}))

import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { KnowledgeWorkspaceLayout } from './KnowledgeWorkspaceLayout'

describe('KnowledgeWorkspaceLayout persisted resize behavior', () => {
  beforeEach(() => useKnowledgeWorkspaceStore.getState().resetWorkspace())

  it('persists sizes[0] from ResizablePanelGroup.onLayout', () => {
    useKnowledgeWorkspaceStore.getState().splitPane('pane-1', 'horizontal')
    const layout = useKnowledgeWorkspaceStore.getState().layout
    if (layout.type !== 'split') throw new Error('expected a split fixture')

    render(
      <KnowledgeWorkspaceLayout renderPane={(pane) => <div>{pane.id}</div>} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Report layout' }))

    expect(useKnowledgeWorkspaceStore.getState().layout).toMatchObject({
      type: 'split', id: layout.id, firstSize: 35,
    })
  })
})
