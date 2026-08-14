import fs from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FolioPage } from './folio/FolioPage'
import { THEME_BY_ID } from '@/lib/themes/catalog'
import { SourceApprovalPanel } from '@/components/research/SourceApprovalPanel'

const source = (file: string) => fs.readFileSync(path.resolve(__dirname, file), 'utf8')

describe('Luminous Folio accessibility', () => {
  it('exposes one named main landmark with a single page heading and a keyboard-reachable action', () => {
    render(
      <FolioPage title="Research workspace" eyebrow="Research Core" actions={<button type="button">Create notebook</button>}>
        <section aria-labelledby="working-notes"><h2 id="working-notes">Working notes</h2><p>Local-first research.</p></section>
      </FolioPage>,
    )

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('main', { name: 'Research workspace' })).toContainElement(
      screen.getByRole('button', { name: 'Create notebook' }),
    )
  })

  it('keeps interactive folio controls visible and touch-sized without relying on motion or glass', () => {
    const globals = source('../../app/globals.css')
    const tokens = source('./tokens.css')
    const folio = source('./folio/folio.css')

    expect(globals).toMatch(/:focus-visible\s*\{[\s\S]*outline:\s*3px solid var\(--ring\)/)
    expect(folio).toMatch(/\[data-dn-folio-tab\]\s*\{[\s\S]*min-block-size:\s*44px[\s\S]*min-inline-size:\s*44px/)
    expect(tokens).toContain('html[data-dn-transparency="solid"] .dn-glass')
    expect(tokens).toContain('backdrop-filter: none')
    expect(tokens).toContain('html[data-dn-motion="reduced"] .dn-aurora-bg::before')
    expect(tokens).toContain('animation: none')
  })

  it('meets the minimum contrast contract for flagship and high-contrast themes', () => {
    for (const themeId of [
      'research-core-dark',
      'gemini-forward-light',
      'archive-paper',
      'high-contrast-dark',
      'high-contrast-light',
    ] as const) {
      const theme = THEME_BY_ID[themeId]
      expect(contrastRatio(theme.preview.canvas, theme.preview.text)).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(theme.preview.canvas, theme.preview.primary)).toBeGreaterThanOrEqual(3)
    }
  })

  it('exposes semantic visual-system roles for imagery, evidence, focus, and shape', () => {
    const tokens = source('./tokens.css')

    for (const token of [
      '--dn-canvas', '--dn-panel', '--dn-panel-raised', '--dn-selection',
      '--dn-focus', '--dn-image-overlay', '--dn-image-placeholder',
      '--dn-evidence-supported', '--dn-evidence-mixed', '--dn-evidence-unsupported',
      '--dn-radius-control', '--dn-radius-card', '--dn-radius-hero',
    ]) {
      expect(tokens).toContain(token)
    }
  })

  it('keeps evidence receipts outside selectable source labels', () => {
    render(
      <SourceApprovalPanel
        onApprove={() => undefined}
        candidates={[{
          candidate_id: 'evidence',
          url: 'https://example.com/evidence',
          title: 'Evidence result',
          domain: 'example.com',
          snippet: 'Deterministic source receipt.',
          search_query: 'topic',
          decision: 'pending',
          evidence: {
            query: 'topic', provider: 'fixture', title: 'Evidence result', url: 'https://example.com/evidence',
            snippet: '', retrieved_at: '2026-01-01T00:00:00Z', freshness: 'fresh', degraded: false,
            source_fingerprint: 'a'.repeat(64), evidence_id: 'b'.repeat(64),
          },
        }]}
      />,
    )

    expect(screen.getByRole('group', { name: 'Evidence receipt' }).closest('label')).toBeNull()
  })
})

function contrastRatio(first: string, second: string): number {
  const luminance = (value: string) => {
    const channels = [1, 3, 5].map(offset => parseInt(value.slice(offset, offset + 2), 16) / 255)
    const linear = channels.map(channel => (
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    ))
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
  }

  const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a)
  return (lighter + 0.05) / (darker + 0.05)
}
