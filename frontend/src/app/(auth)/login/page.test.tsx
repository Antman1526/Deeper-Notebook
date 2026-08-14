import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import React from 'react'

import LoginPage from './page'

vi.mock('@/components/auth/LoginForm', () => ({
  LoginForm: ({ headingLevel = 1 }: { headingLevel?: 1 | 2 }) => (
    <form data-testid="login-form" onSubmit={(event) => event.preventDefault()}>
      {headingLevel === 1 ? <h1>Deeper Notebook</h1> : <h2>Deeper Notebook</h2>}
      <button type="submit">Sign in</button>
    </form>
  ),
}))

vi.mock('@/components/common/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/deeper-notebook/AuthFolio', () => ({
  AuthFolio: ({ children }: { children: React.ReactNode }) => (
    <main aria-label="Deeper Notebook sign in" data-dn-folio-page="true">
      <h1>Sign in</h1>
      {children}
    </main>
  ),
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: () => process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 === '1',
}))

describe('LoginPage visual presentation boundary', () => {
  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
  })

  it('uses the V2 auth frame without changing the LoginForm action', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '1'
    render(<LoginPage />)

    expect(screen.getByTestId('visual-system-v2-auth-frame')).toHaveAttribute(
      'data-dn-visual-system',
      'v2',
    )
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 2, name: 'Deeper Notebook' })).toBeInTheDocument()

    const submit = screen.getByRole('button', { name: 'Sign in' })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    expect(screen.getByTestId('login-form')).toBeInTheDocument()
  })

  it('keeps the AuthFolio marker and action when V2 is explicitly off', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '0'
    render(<LoginPage />)

    expect(screen.getByTestId('login-form')).toBeInTheDocument()
    expect(screen.getByTestId('login-form').closest('[data-dn-folio-page="true"]')).not.toBeNull()
    expect(screen.queryByTestId('visual-system-v2-auth-frame')).toBeNull()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(2)
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })
})
