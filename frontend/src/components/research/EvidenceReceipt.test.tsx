import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ResearchEvidence } from '@/lib/api/research'

import { EvidenceReceipt } from './EvidenceReceipt'

// Interpolated labels carry the fingerprint, so this suite's t() appends its option values
// to the key (the global setup mock returns the bare key).
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) =>
      options ? `${key} ${Object.values(options).join(' ')}` : key,
  }),
}))

const sourceFingerprint = 'a'.repeat(64)
const evidenceId = 'b'.repeat(64)

const evidence: ResearchEvidence = {
  query: 'topic',
  provider: 'serper',
  title: 'Evidence result',
  url: 'https://example.com/evidence',
  snippet: 'Evidence snippet',
  retrieved_at: '2026-08-08T12:34:56Z',
  freshness: 'fresh',
  degraded: false,
  source_fingerprint: sourceFingerprint,
  evidence_id: evidenceId,
}

describe('EvidenceReceipt', () => {
  it('renders provenance, freshness, retrieval time, and accessible fingerprints', () => {
    render(<EvidenceReceipt evidence={evidence} />)

    expect(screen.getByRole('group', { name: 'research.evidenceReceipt.receipt' })).toHaveAttribute('data-dn-folio-evidence', 'true')
    expect(screen.getByText('serper')).toBeInTheDocument()
    expect(screen.getByText('research.evidenceReceipt.fresh')).toBeInTheDocument()
    expect(screen.getByText(/UTC/)).toBeInTheDocument()
    expect(screen.getByText('aaaaaaaa…aaaaaaaa')).toBeInTheDocument()
    expect(screen.getByText('bbbbbbbb…bbbbbbbb')).toBeInTheDocument()
    expect(screen.getByLabelText(`research.evidenceReceipt.sourceFingerprintAria ${sourceFingerprint}`)).toBeInTheDocument()
    expect(screen.getByLabelText(`research.evidenceReceipt.evidenceFingerprintAria ${evidenceId}`)).toBeInTheDocument()
  })

  it('labels stale degraded evidence in text', () => {
    render(<EvidenceReceipt evidence={{ ...evidence, freshness: 'stale', degraded: true }} />)

    expect(screen.getByText('research.evidenceReceipt.stale')).toBeInTheDocument()
    expect(screen.getByText('research.evidenceReceipt.fallbackProvider')).toBeInTheDocument()
  })

  it('renders unknown freshness without a receipt for legacy candidates', () => {
    const { rerender } = render(<EvidenceReceipt evidence={{ ...evidence, freshness: 'unknown' }} />)

    expect(screen.getByText('research.evidenceReceipt.freshnessUnknown')).toBeInTheDocument()

    rerender(<EvidenceReceipt evidence={null} />)
    expect(screen.queryByRole('group', { name: 'research.evidenceReceipt.receipt' })).not.toBeInTheDocument()
    expect(screen.queryByText('serper')).not.toBeInTheDocument()
  })
})
