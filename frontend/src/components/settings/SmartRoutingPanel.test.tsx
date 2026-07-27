import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: () => <input type="checkbox" />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? _key,
  }),
}))

vi.mock('@/lib/hooks/use-models', () => ({
  useUpdateModelDefaults: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { SmartRoutingPanel } from './SmartRoutingPanel'

describe('SmartRoutingPanel visible environment help', () => {
  it('names only canonical Deeper Notebook environment variables', () => {
    render(
      <SmartRoutingPanel
        defaults={{
          auto_route_enabled: false,
          auto_route_provider_pref: 'auto',
        } as never}
      />,
    )

    expect(
      screen.getByText(/DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT/),
    ).toHaveTextContent('DEEPER_NOTEBOOK_CHAT_PROVIDER')
    expect(screen.queryByText(/OPEN_NOTEBOOK_|ONP_/)).not.toBeInTheDocument()
  })
})
