'use client'

import { useMemo } from 'react'

import type { VaultLink } from '@/lib/api/vault'
import { livePreviewExtension } from '@/lib/vault/live-preview'

import { VaultCodeMirror } from './VaultCodeMirror'

interface VaultLivePreviewProps {
  title: string
  markdown: string
  links: VaultLink[]
  onNavigate: (noteId: string) => void
}

export function VaultLivePreview({
  title,
  markdown,
  links,
  onNavigate,
}: VaultLivePreviewProps) {
  const extensions = useMemo(
    () => [livePreviewExtension({ links, onNavigate })],
    [links, onNavigate],
  )

  return (
    <section className="dn-vault-live-preview" aria-label={`${title} live preview`}>
      <VaultCodeMirror
        ariaLabel={`${title} live preview`}
        markdown={markdown}
        extensions={extensions}
      />
    </section>
  )
}
