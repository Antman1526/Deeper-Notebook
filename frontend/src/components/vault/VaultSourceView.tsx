'use client'

import type { VaultFile } from '@/lib/api/vault'

import { VaultCodeMirror } from './VaultCodeMirror'

interface VaultSourceViewProps {
  title: string
  markdown: string
  file: VaultFile
  onSelectionChange?: (from: number, to: number) => void
}

function metadataValue(value: string | null) {
  return value || 'unknown'
}

export function VaultSourceView({ title, markdown, file, onSelectionChange }: VaultSourceViewProps) {
  return (
    <section className="dn-vault-source-view" aria-label={`${title} source`}>
      <VaultCodeMirror
        ariaLabel={`${title} source`}
        markdown={markdown}
        extensions={[]}
        onSelectionChange={onSelectionChange}
      />
      <dl className="dn-vault-source-status" aria-label="Canonical file metadata">
        <div><dt>Path</dt><dd>{file.relative_path}</dd></div>
        <div><dt>Format</dt><dd>{file.format}</dd></div>
        <div><dt>Encoding</dt><dd>{metadataValue(file.encoding)}</dd></div>
        <div><dt>Newline</dt><dd>{metadataValue(file.newline)}</dd></div>
        <div><dt>Size</dt><dd>{file.size_bytes} bytes</dd></div>
        <div><dt>Hash</dt><dd>{file.content_hash?.slice(0, 12) || 'unknown'}</dd></div>
      </dl>
    </section>
  )
}
