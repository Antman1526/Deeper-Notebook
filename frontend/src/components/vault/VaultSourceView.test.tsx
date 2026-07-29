import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { VaultSourceView } from './VaultSourceView'

const fileFixture = {
  id: 'file:plan',
  note_id: 'note:plan',
  vault_id: 'vault:research',
  relative_path: 'pages/original.md',
  file_kind: 'note',
  format: 'markdown' as const,
  content_hash: null,
  parse_status: 'parsed' as const,
  size_bytes: 0,
  modified_ns: 0,
  encoding: null,
  newline: null,
  deleted_state: 'present' as const,
}

describe('VaultSourceView', () => {
  it('shows exact canonical source and provenance without edit controls', () => {
    render(
      <VaultSourceView
        title="Plan"
        markdown={'---\r\ntitle: Plan\r\n---\r\n# Plan\r\n'}
        file={{
          ...fileFixture,
          relative_path: 'pages/plan.md',
          format: 'obsidian',
          content_hash: 'a'.repeat(64),
          encoding: 'utf-8',
          newline: 'crlf',
          size_bytes: 39,
        }}
      />,
    )

    expect(screen.getByRole('textbox', { name: 'Plan source' }))
      .toHaveAttribute('aria-readonly', 'true')
    expect(screen.getByText('pages/plan.md')).toBeInTheDocument()
    expect(screen.getByText('aaaaaaaaaaaa')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save/i }))
      .not.toBeInTheDocument()
  })
})
