import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from './resizable'

// v0.8.130 — the column splitters gave almost no sign of being draggable until the
// pointer was exactly on the 1px line. The grip pill now answers the handle's own
// hover and drag states (which cover its wider hit area), and a double-click puts
// the columns back to their default widths.
function Workspace({ onReset }: { onReset?: () => void }) {
  return (
    <ResizablePanelGroup direction="horizontal">
      <ResizablePanel defaultSize={50}>left</ResizablePanel>
      <ResizableHandle withHandle onReset={onReset} title="Drag to resize; double-click to reset" />
      <ResizablePanel defaultSize={50}>right</ResizablePanel>
    </ResizablePanelGroup>
  )
}

describe('ResizableHandle', () => {
  it('resets the layout on double-click', () => {
    const onReset = vi.fn()
    const { container } = render(<Workspace onReset={onReset} />)
    const handle = container.querySelector('[data-panel-resize-handle-id]') as HTMLElement
    fireEvent.doubleClick(handle)
    expect(onReset).toHaveBeenCalledOnce()
    expect(handle).toHaveAttribute('title', 'Drag to resize; double-click to reset')
  })

  it('lights its grip from the handle state, not only from a hover on the line', () => {
    const { container } = render(<Workspace />)
    const grip = container.querySelector('[data-dn-resize-grip]') as HTMLElement
    expect(grip).not.toBeNull()
    expect(grip.className).toMatch(/group-data-\[resize-handle-state=hover\]:/)
    expect(grip.className).toMatch(/group-data-\[resize-handle-state=drag\]:bg-primary/)
  })

  it('does nothing on double-click when no reset is wired', () => {
    const { container } = render(<Workspace />)
    const handle = container.querySelector('[data-panel-resize-handle-id]') as HTMLElement
    expect(() => fireEvent.doubleClick(handle)).not.toThrow()
  })
})
