import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import CapturePage from './page'

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/capture/CaptureInbox', () => ({
  CaptureInbox: () => <div>Capture inbox</div>,
}))

describe('CapturePage', () => {
  it('places the existing inbox inside the Collect folio frame', () => {
    render(<CapturePage />)

    expect(screen.getByRole('main', { name: 'Capture' })).toBeInTheDocument()
    expect(screen.getByText('Collect')).toBeInTheDocument()
    expect(screen.getByText('Capture inbox')).toBeInTheDocument()
  })
})
