'use client'

import { useMemo } from 'react'

import type { VaultLink } from '@/lib/api/vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import { livePreviewExtension } from '@/lib/vault/live-preview'

import { VaultCodeMirror } from './VaultCodeMirror'

interface VaultLivePreviewProps {
  title: string
  markdown: string
  links: VaultLink[]
  onNavigate: (noteId: string) => void
  onSelectionChange?: (from: number, to: number) => void
}

export function VaultLivePreview({
  title,
  markdown,
  links,
  onNavigate,
  onSelectionChange,
}: VaultLivePreviewProps) {
  const { t } = useTranslation()
  const extensions = useMemo(
    () => [livePreviewExtension({ links, onNavigate, source: markdown })],
    [links, markdown, onNavigate],
  )

  return (
    <section className="dn-vault-live-preview" aria-label={t('knowledge.vaultLivePreview.livePreview', { title })}>
      <VaultCodeMirror
        ariaLabel={t('knowledge.vaultLivePreview.livePreview', { title })}
        markdown={markdown}
        extensions={extensions}
        onSelectionChange={onSelectionChange}
      />
    </section>
  )
}
