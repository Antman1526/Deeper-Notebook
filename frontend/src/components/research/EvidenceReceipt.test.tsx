import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ResearchEvidence } from '@/lib/api/research'

import { EvidenceReceipt } from './EvidenceReceipt'

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

    expect(screen.getByRole('group', { name: 'Evidence receipt' })).toHaveAttribute('data-dn-folio-evidence', 'true')
    expect(screen.getByText('serper')).toBeInTheDocument()
    expect(screen.getByText('Fresh')).toBeInTheDocument()
    expect(screen.getByText(/UTC/)).toBeInTheDocument()
    expect(screen.getByText('aaaaaaaa…aaaaaaaa')).toBeInTheDocument()
    expect(screen.getByText('bbbbbbbb…bbbbbbbb')).toBeInTheDocument()
    expect(screen.getByLabelText(`Source fingerprint: ${sourceFingerprint}`)).toBeInTheDocument()
    expect(screen.getByLabelText(`Evidence fingerprint: ${evidenceId}`)).toBeInTheDocument()
  })

  it('labels stale degraded evidence in text', () => {
    render(<EvidenceReceipt evidence={{ ...evidence, freshness: 'stale', degraded: true }} />)

    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('Fallback provider')).toBeInTheDocument()
  })

  it('renders unknown freshness without a receipt for legacy candidates', () => {
    const { rerender } = render(<EvidenceReceipt evidence={{ ...evidence, freshness: 'unknown' }} />)

    expect(screen.getByText('Freshness unknown')).toBeInTheDocument()

    rerender(<EvidenceReceipt evidence={null} />)
    expect(screen.queryByRole('group', { name: 'Evidence receipt' })).not.toBeInTheDocument()
    expect(screen.queryByText('serper')).not.toBeInTheDocument()
  })
})
