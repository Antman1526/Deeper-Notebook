import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    onClick,
  }: {
    children: React.ReactNode
    onClick?: () => void
  }) => <button onClick={onClick}>{children}</button>,
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? _key,
  }),
}))

vi.mock('@/lib/hooks/use-db-repair-status', () => ({
  useDbRepairStatus: () => ({ data: { needs_repair: true } }),
}))

import { DbRepairBanner } from './DbRepairBanner'

type RelaunchBridge = { relaunch: ReturnType<typeof vi.fn> }
type RepairWindow = Window & { DN?: RelaunchBridge; ONP?: RelaunchBridge }

function clickRepairRestart() {
  render(<DbRepairBanner />)
  fireEvent.click(screen.getByText('Repair & restart'))
}

describe('DbRepairBanner desktop bridge precedence', () => {
  beforeEach(() => {
    delete (window as RepairWindow).DN
    delete (window as RepairWindow).ONP
  })

  afterEach(() => {
    delete (window as RepairWindow).DN
    delete (window as RepairWindow).ONP
  })

  it('uses the canonical DN relaunch bridge when it is available', () => {
    const canonical = { relaunch: vi.fn(() => true) }
    ;(window as RepairWindow).DN = canonical

    clickRepairRestart()

    expect(canonical.relaunch).toHaveBeenCalledOnce()
  })

  it('falls back to the legacy ONP relaunch bridge when DN is absent', () => {
    const legacy = { relaunch: vi.fn(() => true) }
    ;(window as RepairWindow).ONP = legacy

    clickRepairRestart()

    expect(legacy.relaunch).toHaveBeenCalledOnce()
  })

  it('gives the canonical DN bridge precedence when both bridges exist', () => {
    const canonical = { relaunch: vi.fn(() => true) }
    const legacy = { relaunch: vi.fn(() => true) }
    ;(window as RepairWindow).DN = canonical
    ;(window as RepairWindow).ONP = legacy

    clickRepairRestart()

    expect(canonical.relaunch).toHaveBeenCalledOnce()
    expect(legacy.relaunch).not.toHaveBeenCalled()
  })
})
