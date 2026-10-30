import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BackupProvenancePanel } from './BackupProvenancePanel'

// Tests mock `t` as the identity on keys; interpolated numbers are appended so the
// formatting assertions below still see the computed value.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { value?: string | number; count?: number }) => {
      const v = opts?.value ?? opts?.count
      return v === undefined ? key : `${key}:${v}`
    },
  }),
}))

const baseSnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'ready',
  reasons: [],
  readiness: { state: 'ready', database: 'online', migrations: 'applied' },
  startup: { state: 'ready', stages: [] },
  updates: { state: 'ready', enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready', ready: 2, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready', projected: 2, unchanged: 1, failed: 0 },
  backup: {
    state: 'ready',
    freshness: 'valid',
    integrity: 'unknown',
    file_count: 1,
    newest_age_seconds: 30,
    newest_size_bytes: 2048,
    newest_timestamp: '2026-08-11T00:00:00+00:00',
  },
  provenance: {
    state: 'ready',
    mount_count: 2,
    external_read_only_count: 2,
    source_fingerprint_state: 'available',
  },
}

describe('BackupProvenancePanel', () => {
  it('renders valid local backup metadata and aggregate read-only provenance', () => {
    render(<BackupProvenancePanel snapshot={baseSnapshot} />)

    expect(screen.getByRole('region', { name: 'workspace.backupProvenancePanel.ariaLabel' })).toHaveTextContent('workspace.backupProvenancePanel.receiptValid')
    expect(screen.getByText('workspace.backupProvenancePanel.sizeKb:2')).toBeInTheDocument()
    expect(screen.getByText('workspace.backupProvenancePanel.integrityNotVerified')).toBeInTheDocument()
    expect(screen.getByText('workspace.backupProvenancePanel.externalSpaceOther:2')).toBeInTheDocument()
    expect(screen.getByText('workspace.backupProvenancePanel.fingerprintsRecorded')).toBeInTheDocument()
  })

  it.each([
    ['stale', 'workspace.backupProvenancePanel.receiptStale', 'workspace.backupProvenancePanel.messageStale'],
    ['unknown', 'workspace.backupProvenancePanel.receiptUnknown', 'workspace.backupProvenancePanel.messageUnknown'],
  ] as const)('renders %s backup state without inventing details', (freshness, label, message) => {
    render(
      <BackupProvenancePanel
        snapshot={{
          ...baseSnapshot,
          backup: {
            ...baseSnapshot.backup,
            freshness,
            newest_age_seconds: freshness === 'stale' ? 172_801 : null,
            newest_size_bytes: freshness === 'stale' ? 2048 : null,
            newest_timestamp: freshness === 'stale' ? baseSnapshot.backup.newest_timestamp : null,
          },
        }}
      />,
    )

    expect(screen.getByRole('region', { name: 'workspace.backupProvenancePanel.ariaLabel' })).toHaveTextContent(label)
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.queryByText(/\/private|Volumes|private source content/)).not.toBeInTheDocument()
  })

  it('uses plain read-only wording and never renders an operation control', () => {
    render(
      <BackupProvenancePanel
        snapshot={{
          ...baseSnapshot,
          provenance: {
            state: 'ready',
            mount_count: 1,
            external_read_only_count: 1,
            source_fingerprint_state: 'unknown',
          },
        }}
      />,
    )

    expect(screen.getByText('workspace.backupProvenancePanel.externalSpaceOne:1')).toBeInTheDocument()
    expect(screen.getByText('workspace.backupProvenancePanel.fingerprintsUnavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
