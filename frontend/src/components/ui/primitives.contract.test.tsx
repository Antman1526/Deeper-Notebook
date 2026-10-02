import fs from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert } from './alert'
import { Badge } from './badge'
import { Button } from './button'
import { Input } from './input'
import { Select, SelectTrigger, SelectValue } from './select'

// Phase 1 of the 2026-09-30 UI audit: the primitives follow the token spec
// (UI audit 4.2). The whole ui/ folder is scanned so a new primitive cannot
// reintroduce what was removed here.
const uiDir = __dirname
const sources = fs
  .readdirSync(uiDir)
  .filter((file) => file.endsWith('.tsx') && !file.includes('.test.'))
  .map((file) => ({ file, source: fs.readFileSync(path.join(uiDir, file), 'utf8') }))

describe('ui/ primitives source contract', () => {
  // The global 3px :focus-visible outline (globals.css) is the one focus
  // indicator. Primitives drew a second, translucent box-shadow ring on top.
  it.each(sources)('$file draws no box-shadow focus ring of its own', ({ source }) => {
    expect(source).not.toMatch(/\bfocus(-visible)?:ring(-offset)?(-\[?[\w./]+\]?)?/)
  })

  it.each(sources)('$file animates named properties, never transition-all', ({ source }) => {
    expect(source).not.toMatch(/\btransition-all\b/)
  })

  it.each(sources)('$file does not scale on hover or press', ({ source }) => {
    expect(source).not.toMatch(/\b(hover|active|group-hover):scale-/)
  })

  it.each(sources.filter(({ file }) => /dialog/.test(file)))('$file uses a solid surface, not frosted glass', ({ source }) => {
    expect(source).not.toMatch(/backdrop-blur/)
  })

  it('menu rows and select options use the 12px item radius', () => {
    for (const file of ['dropdown-menu.tsx', 'select.tsx', 'command.tsx']) {
      const source = sources.find((entry) => entry.file === file)!.source
      expect(source, file).not.toMatch(/\brounded-sm\b/)
    }
  })

  it('tooltips are a neutral inverse surface, not the brand colour', () => {
    const source = sources.find((entry) => entry.file === 'tooltip.tsx')!.source
    expect(source).toMatch(/bg-foreground text-background/)
    expect(source).not.toMatch(/bg-primary/)
  })
})

describe('Button', () => {
  // v0.8.130 — premium pass (user decision 2026-10-01): rectangular, not a pill.
  it('is a 40px rectangle (8px corners) by default', () => {
    render(<Button>Save</Button>)
    const button = screen.getByRole('button', { name: 'Save' })
    expect(button).toHaveClass('rounded-md', 'h-10')
    expect(button).not.toHaveClass('rounded-full')
  })

  it.each([
    ['sm', 'h-8'],
    ['lg', 'h-12'],
    ['icon', 'size-10'],
  ] as const)('size %s is %s', (size, height) => {
    render(<Button size={size} aria-label="Act">A</Button>)
    expect(screen.getByRole('button', { name: 'Act' })).toHaveClass(height)
  })

  it('puts the contrast-checked foreground on the destructive fill', () => {
    render(<Button variant="destructive">Delete</Button>)
    const button = screen.getByRole('button', { name: 'Delete' })
    expect(button).toHaveClass('bg-destructive', 'text-destructive-foreground')
    expect(button).not.toHaveClass('text-white')
  })
})

describe('Badge', () => {
  it('is a pill', () => {
    render(<Badge>New</Badge>)
    expect(screen.getByText('New')).toHaveClass('rounded-full')
  })

  it.each(['success', 'warning', 'info'] as const)('has a soft %s variant', (variant) => {
    render(<Badge variant={variant}>{variant}</Badge>)
    expect(screen.getByText(variant)).toHaveClass(`bg-${variant}-soft`, `text-${variant}-ink`)
  })
})

describe('Alert', () => {
  it.each(['success', 'warning', 'info', 'destructive'] as const)('has a soft %s variant', (variant) => {
    render(<Alert variant={variant}>{variant}</Alert>)
    expect(screen.getByRole('alert')).toHaveClass(`bg-${variant}-soft`, `text-${variant}-ink`)
  })
})

describe('form controls', () => {
  it('Input is 40px tall', () => {
    render(<Input aria-label="Name" />)
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveClass('h-10')
  })

  it('Select trigger matches the Input height', () => {
    render(
      <Select>
        <SelectTrigger aria-label="Model">
          <SelectValue placeholder="Pick" />
        </SelectTrigger>
      </Select>,
    )
    expect(screen.getByRole('combobox', { name: 'Model' }).className).toMatch(/data-\[size=default\]:h-10/)
  })
})
