import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ pathname: '/knowledge' }))

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
}))

import { GuidedTipsProvider, placeCallout } from './GuidedTipsProvider'
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

    expect(await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })).toBeVisible()
    expect(screen.getByText('workspace.catalog.knowledgeOverviewBody')).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'workspace.guidedTipsProvider.gotIt' }))

    expect(screen.queryByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })).not.toBeInTheDocument()
  })

  // v0.8.130 — rendered inside the shell, the tip's z-index only counted within the
  // navigator's stacking context, so page controls (the notebook card's z-10 actions)
  // painted over its "Got it" button at 1440px. It is portalled to <body>.
  it('renders the tip at the document root, above every shell stacking context', async () => {
    const { container } = renderTip()
    const tip = await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })
    expect(tip.parentElement).toBe(document.body)
    expect(container.contains(tip)).toBe(false)
  })

  it('suppresses the tip while a modal is open', async () => {
    const modal = document.createElement('div')
    modal.setAttribute('aria-modal', 'true')
    document.body.append(modal)

    renderTip()

    await waitFor(() => {
      expect(screen.queryByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })).not.toBeInTheDocument()
    })
  })

  it('fails closed when its expected anchor is missing', async () => {
    renderTip('/sources')

    await waitFor(() => {
      expect(screen.queryByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })).not.toBeInTheDocument()
    })
  })

  it('disables all future tips without completing the catalog item', async () => {
    renderTip()

    fireEvent.click(await screen.findByRole('button', { name: 'workspace.guidedTipsProvider.dontShowAgain' }))

    expect(useGuidedTipsStore.getState().enabled).toBe(false)
    expect(useGuidedTipsStore.getState().completed).toEqual({})
  })

  it('dismisses only the current version when Escape is pressed', async () => {
    renderTip()

    await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(useGuidedTipsStore.getState().completed).toEqual({ 'knowledge-overview': 2 })
  })

  it('does not complete a rendered tip after its expected anchor is removed', async () => {
    const anchor = document.createElement('button')
    anchor.setAttribute('data-guided-tip-anchor', '/knowledge')
    document.body.append(anchor)
    render(<GuidedTipsProvider />)

    await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })
    anchor.remove()
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(useGuidedTipsStore.getState().completed).toEqual({})
  })

  it('does not create a focus trap', async () => {
    renderTip()

    const tip = await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })

    expect(tip).not.toHaveAttribute('aria-modal')
    expect(tip).not.toHaveAttribute('tabindex')
  })
})

// v0.8.130 — the callout sits right of its rail anchor, which is exactly where the main
// column's <h1> starts, so it was drawn over the page title. jsdom has no layout, so the
// geometry is a pure function over plain rects.
describe('placeCallout', () => {
  const viewport = { width: 1440, height: 900 }
  const calloutHeight = 180
  const railLink = { top: 100, left: 16, right: 240, bottom: 130 }

  it('keeps the old position (right of the anchor, top-aligned) when the heading is clear', () => {
    const heading = { top: 400, left: 280, right: 700, bottom: 440 }

    expect(placeCallout({ anchor: railLink, heading, calloutHeight, viewport })).toEqual({
      top: 100,
      left: 252,
    })
  })

  it('moves below the heading when the default position would cover it', () => {
    const heading = { top: 96, left: 280, right: 700, bottom: 140 }

    expect(placeCallout({ anchor: railLink, heading, calloutHeight, viewport })).toEqual({
      top: 152,
      left: 252,
    })
  })

  it('treats a gap smaller than the anchor gap as overlapping', () => {
    // The default callout spans top 20..200.
    const anchor = { top: 20, left: 16, right: 240, bottom: 50 }

    // Heading begins 5px under the callout: closer than the 12px gap, so it moves below it.
    const tooClose = placeCallout({
      anchor,
      heading: { top: 205, left: 280, right: 700, bottom: 240 },
      calloutHeight,
      viewport,
    })
    expect(tooClose.top).toBe(252)

    // Exactly 12px clear is not an intersection.
    const clear = placeCallout({
      anchor,
      heading: { top: 212, left: 280, right: 700, bottom: 240 },
      calloutHeight,
      viewport,
    })
    expect(clear.top).toBe(20)
  })

  it('does not move when the heading is horizontally clear of the callout', () => {
    // Heading starts well to the right of the callout (252 + 320 = 572).
    const heading = { top: 96, left: 700, right: 1100, bottom: 140 }

    expect(placeCallout({ anchor: railLink, heading, calloutHeight, viewport })).toEqual({
      top: 100,
      left: 252,
    })
  })

  it('uses the old formula when there is no heading', () => {
    expect(placeCallout({ anchor: railLink, heading: null, calloutHeight, viewport })).toEqual({
      top: 100,
      left: 252,
    })
  })

  it('clamps inside the viewport when the anchor is near the bottom', () => {
    const anchor = { top: 880, left: 16, right: 240, bottom: 900 }

    expect(placeCallout({ anchor, heading: null, calloutHeight, viewport })).toEqual({
      top: 900 - calloutHeight - 16,
      left: 252,
    })
  })

  it('clamps inside the viewport when clearing the heading would push it off the bottom', () => {
    const heading = { top: 96, left: 280, right: 700, bottom: 700 }
    const placed = placeCallout({ anchor: railLink, heading, calloutHeight, viewport })

    expect(placed.top).toBe(900 - calloutHeight - 16)
    expect(placed.top).toBeGreaterThanOrEqual(16)
  })

  it('clamps horizontally against a narrow viewport', () => {
    const narrow = { width: 500, height: 900 }
    const anchor = { top: 100, left: 16, right: 450, bottom: 130 }
    const placed = placeCallout({ anchor, heading: null, calloutHeight, viewport: narrow })

    expect(placed.left).toBe(500 - 320 - 16)
    expect(placed.left).toBeGreaterThanOrEqual(16)
  })

  it('stays fully on screen on a short viewport where it cannot clear the heading', () => {
    const short = { width: 1440, height: 300 }
    const anchor = { top: 50, left: 16, right: 240, bottom: 80 }
    const heading = { top: 40, left: 280, right: 700, bottom: 120 }
    const placed = placeCallout({ anchor, heading, calloutHeight, viewport: short })

    expect(placed.top).toBeGreaterThanOrEqual(16)
    expect(placed.top + calloutHeight).toBeLessThanOrEqual(300 - 16)
    expect(placed.left).toBeGreaterThanOrEqual(16)
    expect(placed.left + 320).toBeLessThanOrEqual(1440 - 16)
  })
})
