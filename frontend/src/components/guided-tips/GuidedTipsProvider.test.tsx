import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ pathname: '/knowledge' }))

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
}))

import { GuidedTipsProvider } from './GuidedTipsProvider'
import { useGuidedTipsStore } from '@/lib/stores/guided-tips-store'

function renderTip(anchor = '/knowledge') {
  return render(
    <>
      <button data-guided-tip-anchor={anchor}>Knowledge</button>
      <GuidedTipsProvider />
    </>,
  )
}

describe('GuidedTipsProvider', () => {
  beforeEach(() => {
    navigation.pathname = '/knowledge'
    localStorage.clear()
    useGuidedTipsStore.setState({ enabled: true, completed: {} })
  })

  afterEach(() => {
    document.querySelector('[aria-modal="true"]')?.remove()
    useGuidedTipsStore.setState({ enabled: true, completed: {} })
  })

  it('shows the path-matched knowledge tip and dismisses it with Got it', async () => {
    renderTip()

    expect(await screen.findByRole('note', { name: 'Notebook Index tip' })).toBeVisible()
    expect(screen.getByText(/read-only external vaults/)).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Got it' }))

    expect(screen.queryByRole('note', { name: 'Notebook Index tip' })).not.toBeInTheDocument()
  })

  it('suppresses the tip while a modal is open', async () => {
    const modal = document.createElement('div')
    modal.setAttribute('aria-modal', 'true')
    document.body.append(modal)

    renderTip()

    await waitFor(() => {
      expect(screen.queryByRole('note', { name: 'Notebook Index tip' })).not.toBeInTheDocument()
    })
  })

  it('fails closed when its expected anchor is missing', async () => {
    renderTip('/sources')

    await waitFor(() => {
      expect(screen.queryByRole('note', { name: 'Knowledge workspace tip' })).not.toBeInTheDocument()
    })
  })

  it('disables all future tips without completing the catalog item', async () => {
    renderTip()

    fireEvent.click(await screen.findByRole('button', { name: "Don't show again" }))

    expect(useGuidedTipsStore.getState().enabled).toBe(false)
    expect(useGuidedTipsStore.getState().completed).toEqual({})
  })

  it('dismisses only the current version when Escape is pressed', async () => {
    renderTip()

    await screen.findByRole('note', { name: 'Notebook Index tip' })
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(useGuidedTipsStore.getState().completed).toEqual({ 'knowledge-overview': 2 })
  })

  it('does not complete a rendered tip after its expected anchor is removed', async () => {
    const anchor = document.createElement('button')
    anchor.setAttribute('data-guided-tip-anchor', '/knowledge')
    document.body.append(anchor)
    render(<GuidedTipsProvider />)

    await screen.findByRole('note', { name: 'Notebook Index tip' })
    anchor.remove()
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(useGuidedTipsStore.getState().completed).toEqual({})
  })

  it('does not create a focus trap', async () => {
    renderTip()

    const tip = await screen.findByRole('note', { name: 'Notebook Index tip' })

    expect(tip).not.toHaveAttribute('aria-modal')
    expect(tip).not.toHaveAttribute('tabindex')
  })
})
