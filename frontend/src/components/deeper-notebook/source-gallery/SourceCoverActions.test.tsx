import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SourceCoverActions } from './SourceCoverActions'

function openActions(): void {
  fireEvent.click(screen.getByRole('button', { name: 'Actions for First source' }))
}

describe('SourceCoverActions', () => {
  it('exposes one accessible menu trigger and dispatches each action once', () => {
    const onRefresh = vi.fn()
    const onRemove = vi.fn()
    const onDelete = vi.fn()

    render(
      <SourceCoverActions
        title="First source"
        pending={false}
        visualsDisabled={false}
        onRefresh={onRefresh}
        onRemove={onRemove}
        onDelete={onDelete}
      />,
    )

    const trigger = screen.getByRole('button', { name: 'Actions for First source' })
    expect(trigger).toBeVisible()
    openActions()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Refresh visual' }))
    openActions()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove visual' }))
    openActions()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete source' }))

    expect(onRefresh).toHaveBeenCalledOnce()
    expect(onRemove).toHaveBeenCalledOnce()
    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('disables only visual mutations while a matching cover is pending', () => {
    const onDelete = vi.fn()

    render(
      <SourceCoverActions
        title="First source"
        pending
        visualsDisabled={false}
        onRefresh={vi.fn()}
        onRemove={vi.fn()}
        onDelete={onDelete}
      />,
    )

    openActions()
    expect(screen.getByRole('menuitem', { name: 'Refresh visual' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: 'Remove visual' })).toHaveAttribute('aria-disabled', 'true')
    const deleteItem = screen.getByRole('menuitem', { name: 'Delete source' })
    expect(deleteItem).not.toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(deleteItem)
    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('hides visual actions when the backend capability is off but keeps Delete', () => {
    render(
      <SourceCoverActions
        title="First source"
        pending={false}
        visualsDisabled
        onRefresh={vi.fn()}
        onRemove={vi.fn()}
        onDelete={vi.fn()}
      />,
    )

    openActions()
    expect(screen.queryByRole('menuitem', { name: 'Refresh visual' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Remove visual' })).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Delete source' })).toBeVisible()
  })
})
