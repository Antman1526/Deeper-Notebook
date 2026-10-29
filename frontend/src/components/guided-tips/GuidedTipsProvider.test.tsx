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

    expect(placeCallout({ anchor: railLink, heading, calloutHeight, viewport })).toMatchObject({
      top: 100,
      left: 252,
    })
  })

  it('moves below the heading when the default position would cover it', () => {
    const heading = { top: 96, left: 280, right: 700, bottom: 140 }

    expect(placeCallout({ anchor: railLink, heading, calloutHeight, viewport })).toMatchObject({
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

    expect(placeCallout({ anchor: railLink, heading, calloutHeight, viewport })).toMatchObject({
      top: 100,
      left: 252,
    })
  })

  it('uses the old formula when there is no heading', () => {
    expect(placeCallout({ anchor: railLink, heading: null, calloutHeight, viewport })).toMatchObject({
      top: 100,
      left: 252,
    })
  })

  it('clamps inside the viewport when the anchor is near the bottom', () => {
    const anchor = { top: 880, left: 16, right: 240, bottom: 900 }

    expect(placeCallout({ anchor, heading: null, calloutHeight, viewport })).toMatchObject({
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

  // v0.8.130 — a pointer is only honest while the callout really is beside its anchor.
  describe('pointer', () => {
    it('points at the anchor centre, relative to the callout top, when beside it', () => {
      // Anchor centre is 115, callout top is 100.
      expect(placeCallout({ anchor: railLink, heading: null, calloutHeight, viewport }).pointer)
        .toEqual({ top: 15 })
    })

    it('is null when the callout was pushed below the heading, away from the anchor', () => {
      const heading = { top: 96, left: 280, right: 700, bottom: 140 }
      const placed = placeCallout({ anchor: railLink, heading, calloutHeight, viewport })

      expect(placed.top).toBe(152)
      expect(placed.pointer).toBeNull()
    })

    it('is clamped to 12px from the callout top edge', () => {
      const anchor = { top: 100, left: 16, right: 240, bottom: 104 }

      expect(placeCallout({ anchor, heading: null, calloutHeight, viewport }).pointer)
        .toEqual({ top: 12 })
    })

    it('is clamped to 12px from the callout bottom edge', () => {
      // Callout clamped to 704..884; the anchor centre (882) is 178 below its top.
      const anchor = { top: 878, left: 16, right: 240, bottom: 886 }

      expect(placeCallout({ anchor, heading: null, calloutHeight, viewport }).pointer)
        .toEqual({ top: calloutHeight - 12 })
    })

    it('is null when clamping leaves the anchor centre outside the callout', () => {
      // The callout is clamped down to the 16px inset; the anchor centre (2) is above it.
      const short = { width: 1440, height: 300 }
      const anchor = { top: 0, left: 16, right: 240, bottom: 4 }

      expect(placeCallout({ anchor, heading: null, calloutHeight, viewport: short }).pointer)
        .toBeNull()
    })

    it('is null when horizontal clamping puts the callout over the anchor', () => {
      const narrow = { width: 500, height: 900 }
      const anchor = { top: 100, left: 16, right: 450, bottom: 130 }

      expect(placeCallout({ anchor, heading: null, calloutHeight, viewport: narrow }).pointer)
        .toBeNull()
    })
  })
})

// v0.8.130 — when the callout is pushed below the heading it no longer sits beside its
// navigation item, so the anchor itself carries a marker the stylesheet turns into a ring.
describe('GuidedTipsProvider active anchor marker', () => {
  const ACTIVE = 'data-guided-tip-active'

  beforeEach(() => {
    navigation.pathname = '/knowledge'
    localStorage.clear()
    useGuidedTipsStore.setState({ enabled: true, completed: {} })
  })

  afterEach(() => {
    document.querySelector('[aria-modal="true"]')?.remove()
    useGuidedTipsStore.setState({ enabled: true, completed: {} })
  })

  it('marks the anchor while the tip shows and unmarks it after Got it', async () => {
    renderTip()
    const anchor = screen.getByRole('button', { name: 'Knowledge' })
    await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })

    expect(anchor).toHaveAttribute(ACTIVE, 'true')

    fireEvent.click(screen.getByRole('button', { name: 'workspace.guidedTipsProvider.gotIt' }))

    expect(anchor).not.toHaveAttribute(ACTIVE)
  })

  it('unmarks the anchor after Do not show again', async () => {
    renderTip()
    const anchor = screen.getByRole('button', { name: 'Knowledge' })

    fireEvent.click(await screen.findByRole('button', { name: 'workspace.guidedTipsProvider.dontShowAgain' }))

    expect(anchor).not.toHaveAttribute(ACTIVE)
  })

  it('unmarks the anchor after Escape', async () => {
    renderTip()
    const anchor = screen.getByRole('button', { name: 'Knowledge' })
    await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(anchor).not.toHaveAttribute(ACTIVE)
  })

  it('unmarks the anchor while a modal suspends the tip, and marks it again after', async () => {
    renderTip()
    const anchor = screen.getByRole('button', { name: 'Knowledge' })
    await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })

    const modal = document.createElement('div')
    modal.setAttribute('aria-modal', 'true')
    document.body.append(modal)

    await waitFor(() => expect(anchor).not.toHaveAttribute(ACTIVE))

    modal.remove()
    // Removing a node is a childList mutation, which recomputes the tip.
    await waitFor(() => expect(anchor).toHaveAttribute(ACTIVE, 'true'))
  })

  it('unmarks a document-level anchor when the provider unmounts', async () => {
    const anchor = document.createElement('button')
    anchor.setAttribute('data-guided-tip-anchor', '/knowledge')
    document.body.append(anchor)
    const { unmount } = render(<GuidedTipsProvider />)
    await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })
    expect(anchor).toHaveAttribute(ACTIVE, 'true')

    unmount()

    expect(anchor).not.toHaveAttribute(ACTIVE)
    anchor.remove()
  })

  it('renders the pointer, hidden from assistive tech, when the callout is beside the anchor', async () => {
    const rect = (top: number, left: number, width: number, height: number) =>
      ({ top, left, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect
    const spy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      if (this.hasAttribute('data-guided-tip-anchor')) return rect(100, 16, 224, 30)
      if (this.getAttribute('role') === 'note') return rect(0, 0, 320, 180)
      return rect(0, 0, 0, 0)
    })

    try {
      renderTip()
      const tip = await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })
      // jsdom has no layout, so the anchor rect is faked: centre 115, callout top 100.
      await waitFor(() => expect(tip.querySelector('[data-guided-tip-pointer]')).not.toBeNull())
      const pointer = tip.querySelector<HTMLElement>('[data-guided-tip-pointer]')

      expect(pointer).toHaveAttribute('aria-hidden', 'true')
      expect(pointer?.style.top).toBe('10px')
    } finally {
      spy.mockRestore()
    }
  })

  it('draws no pointer when the callout is nowhere near the anchor', async () => {
    renderTip()
    const tip = await screen.findByRole('note', { name: 'workspace.guidedTipsProvider.ariaLabel' })

    // Unmocked jsdom rects are all zero: the anchor centre is outside the clamped callout.
    expect(tip.querySelector('[data-guided-tip-pointer]')).toBeNull()
  })
})
