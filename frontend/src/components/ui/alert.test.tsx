import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert, AlertDescription, AlertTitle } from './alert'

// v0.8.130 — Phase 4b of the 2026-09-30 UI audit: an alert's title is not a heading. A
// fixed <h5> dropped a fifth-level heading into whatever page showed the alert,
// breaking the heading order (an h1 page with an alert jumped straight to h5).
describe('Alert', () => {
  it('titles the alert without adding a heading to the page outline', () => {
    render(
      <Alert>
        <AlertTitle>Model unavailable</AlertTitle>
        <AlertDescription>Pick another model in Settings.</AlertDescription>
      </Alert>,
    )

    expect(screen.queryByRole('heading')).toBeNull()
    expect(screen.getByText('Model unavailable')).toHaveAttribute('data-slot', 'alert-title')
  })
})
