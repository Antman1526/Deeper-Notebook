import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useConfirm } from './use-confirm'

// v0.8.130 — Phase 4c of the 2026-09-30 UI audit: the app's confirmations use its own
// dialog, not the browser's native confirm() (unstyled, untranslatable, and blocking).

function Harness({ onResult }: { onResult: (value: boolean) => void }) {
  const { confirm, dialog } = useConfirm()
  return (
    <>
      <button
        type="button"
        onClick={async () => onResult(await confirm({
          title: 'Delete artifact?',
          description: 'This cannot be undone.',
          confirmText: 'Delete',
          destructive: true,
        }))}
      >
        Ask
      </button>
      {dialog}
    </>
  )
}

describe('useConfirm', () => {
  it('resolves true when confirmed', async () => {
    const results: boolean[] = []
    render(<Harness onResult={(value) => results.push(value)} />)

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('alertdialog', { name: 'Delete artifact?' })).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    })

    expect(results).toEqual([true])
  })

  it('resolves false when cancelled', async () => {
    const results: boolean[] = []
    render(<Harness onResult={(value) => results.push(value)} />)

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByRole('alertdialog')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }))
    })

    expect(results).toEqual([false])
  })

  it('styles a destructive confirmation as a destructive button', async () => {
    render(<Harness onResult={() => undefined} />)

    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    const action = await screen.findByRole('button', { name: 'Delete' })
    // buttonVariants({ variant: 'destructive' }): the destructive foreground, not the
    // primary button's text colour on a red fill (dark text on red in dark themes).
    expect(action.className).toContain('bg-destructive')
    expect(action.className).toContain('text-destructive-foreground')
    expect(action.className).not.toContain('text-primary-foreground')
  })
})
