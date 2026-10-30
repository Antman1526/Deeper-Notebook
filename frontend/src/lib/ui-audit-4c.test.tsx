// v0.8.130 — Phase 4c of the 2026-09-30 UI audit: confirmations, tooltips, toasts and
// the command bar's route label.

import { readdirSync, readFileSync, statSync } from 'fs'
import { join } from 'path'

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const SRC = join(__dirname, '..')

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      if (entry === 'node_modules' || entry === 'test') continue
      sourceFiles(full, out)
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

const sonnerProps = vi.hoisted(() => ({ value: null as null | Record<string, unknown> }))
vi.mock('sonner', () => ({
  Toaster: (props: Record<string, unknown>) => {
    sonnerProps.value = props
    return null
  },
}))

describe('confirmations', () => {
  it('no component calls the browser’s native confirm()', () => {
    const offenders = sourceFiles(SRC).filter((file) => {
      const source = readFileSync(file, 'utf8').replace(/\/\/.*$/gm, '')
      // A component may name its own function confirm (useConfirm's, or a local one).
      const declaresConfirm = /(const|let|function)\s+confirm\b|\{[^}]*\bconfirm\b[^}]*\}\s*=/.test(source)
      return /window\.confirm\(/.test(source) || (!declaresConfirm && /(^|[^\w.])confirm\(/m.test(source))
    })
    expect(offenders.map((file) => file.replace(SRC, ''))).toEqual([])
    // A synchronous read of every source file: well over 5s while the full suite runs.
  }, 30_000)

  it('Import notebook uses an icon, not an emoji', () => {
    const source = readFileSync(join(SRC, 'app/(dashboard)/notebooks/components/ImportNotebookDialog.tsx'), 'utf8')
    expect(source).not.toContain('📋')
  })
})

describe('tooltips', () => {
  it('wait before opening, and share the app’s provider when there is one', async () => {
    const tooltip = readFileSync(join(SRC, 'components/ui/tooltip.tsx'), 'utf8')
    expect(tooltip).not.toMatch(/delayDuration = 0/)
    const layout = readFileSync(join(SRC, 'app/layout.tsx'), 'utf8')
    expect(layout).toContain('<TooltipProvider')
  })
})

describe('toasts', () => {
  it('style every kind from the theme tokens and follow the active theme', async () => {
    document.documentElement.classList.add('dark')
    const { Toaster } = await import('@/components/ui/sonner')
    render(<Toaster />)

    const style = sonnerProps.value?.style as Record<string, string>
    for (const kind of ['normal', 'success', 'error', 'warning', 'info']) {
      expect(style[`--${kind}-bg`], kind).toMatch(/^var\(--/)
      expect(style[`--${kind}-text`], kind).toMatch(/^var\(--/)
      expect(style[`--${kind}-border`], kind).toMatch(/^var\(--/)
    }
    expect(sonnerProps.value?.theme).toBe('dark')
    document.documentElement.classList.remove('dark')
  })
})

vi.mock('next/navigation', () => ({ usePathname: vi.fn(() => '/notebooks/notebook:1') }))

// Imported up front: loading the command bar's module tree inside the test body took
// over the 5s test timeout on a busy machine.
import { usePathname } from 'next/navigation'
import { CommandBar } from '@/components/deeper-notebook/shell/CommandBar'

describe('command bar route label', () => {
  it('names the route the way the rail does, translated', async () => {
    const label = (pathname: string) => {
      vi.mocked(usePathname).mockReturnValue(pathname)
      const { container, unmount } = render(<CommandBar showBrand={false} />)
      const text = container.querySelector('.dn-command-kicker')?.textContent
      unmount()
      return text
    }

    expect(label('/notebooks/notebook:1')).toBe('navigation.notebooks')
    expect(label('/settings/mcp')).toBe('settings.mcp.navTitle')
    expect(label('/setup-wizard')).toBe('setupWizard.firstRun.title')
    expect(label('/')).toBe('navigation.home')
    expect(screen.queryByText('Setup wizard')).toBeNull()
  })
})
