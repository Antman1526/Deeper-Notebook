import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FolioState } from './folio/FolioState'
import { StatePanel, type StatePanelKind } from './workspace/StatePanel'

// T0-7 — both state surfaces used to print the raw `kind` enum ("loading",
// "empty", "error") as a kicker above the title. It is an implementation detail,
// not copy, and read like a bug on the Home empty state and the error boundary.
// The kind still drives the live-region role and the data attribute.

const panelKinds: StatePanelKind[] = [
  'loading', 'empty', 'processing', 'degraded', 'offline', 'error', 'unavailable',
]
const folioKinds = ['loading', 'empty', 'error', 'offline', 'permission'] as const

describe('StatePanel', () => {
  it.each(panelKinds)('does not print the raw "%s" kind as visible text', (kind) => {
    render(<StatePanel kind={kind} title="Nothing here yet" description="Create something to get started." />)

    expect(screen.queryByText(new RegExp(`^${kind}$`, 'i'))).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nothing here yet' })).toBeInTheDocument()
    expect(screen.getByText('Create something to get started.')).toBeInTheDocument()
  })

  it('still exposes the kind for styling and the right live-region role', () => {
    const { container } = render(<StatePanel kind="error" title="Failed" description="Try again." />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(container.querySelector('[data-dn-state-panel-kind="error"]')).not.toBeNull()
  })
})

describe('FolioState', () => {
  it.each(folioKinds)('does not print the raw "%s" kind as visible text', (kind) => {
    render(<FolioState kind={kind} title="Nothing here yet" description="Create something to get started." />)

    expect(screen.queryByText(new RegExp(`^${kind}$`, 'i'))).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nothing here yet' })).toBeInTheDocument()
  })

  it('still exposes the kind for styling and the right live-region role', () => {
    const { container } = render(<FolioState kind="error" title="Failed" description="Try again." />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(container.querySelector('[data-dn-folio-state-kind="error"]')).not.toBeNull()
  })
})
