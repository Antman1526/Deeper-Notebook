import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const locatePassage = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: { locatePassage },
}))

import { EvidencePeek } from './EvidencePeek'

describe('EvidencePeek', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('uses the exact provided evidence query and displays only the returned passage', async () => {
    locatePassage.mockResolvedValue({ start: 8, end: 28, score: 0.875, snippet: 'Exact returned source passage.' })

    render(<EvidencePeek sourceId="source:one" title="Field notes" evidenceQuery="Exact evidence query" onClose={vi.fn()} />)

    await waitFor(() => expect(locatePassage).toHaveBeenCalledWith('source:one', 'Exact evidence query'))
    expect(await screen.findByText('Exact returned source passage.')).toBeVisible()
    expect(screen.getByText('Match confidence: 88%')).toBeVisible()
  })

  it('does not locate or infer evidence when no existing query is available', () => {
    render(<EvidencePeek sourceId="source:one" title="Field notes" evidenceQuery={null} onClose={vi.fn()} />)

    expect(locatePassage).not.toHaveBeenCalled()
    expect(screen.getByText('Evidence passage unavailable')).toBeVisible()
  })

  it('closes on Escape while retaining scroll and returning focus to the invoker', () => {
    locatePassage.mockResolvedValue(null)
    const onClose = vi.fn()
    const scrollTo = vi.fn()
    Object.defineProperty(window, 'scrollX', { configurable: true, value: 12 })
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 340 })
    window.scrollTo = scrollTo
    const invoker = document.createElement('button')
    invoker.textContent = 'Open evidence'
    document.body.append(invoker)
    invoker.focus()

    render(<EvidencePeek sourceId="source:one" title="Field notes" evidenceQuery="Known match" onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledOnce()
    expect(scrollTo).toHaveBeenCalledWith({ left: 12, top: 340, behavior: 'auto' })
    expect(document.activeElement).toBe(invoker)
  })
})
