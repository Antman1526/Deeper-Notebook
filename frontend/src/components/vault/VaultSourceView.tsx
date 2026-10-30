'use client'

import type { VaultFile } from '@/lib/api/vault'
import { useTranslation } from '@/lib/hooks/use-translation'

import { VaultCodeMirror } from './VaultCodeMirror'

interface VaultSourceViewProps {
  title: string
  markdown: string
  file: VaultFile
  onSelectionChange?: (from: number, to: number) => void
}

export function VaultSourceView({ title, markdown, file, onSelectionChange }: VaultSourceViewProps) {
  const { t } = useTranslation()
  const metadataValue = (value: string | null) => value || t('knowledge.vaultSourceView.unknown')
  return (
    <section className="dn-vault-source-view" aria-label={t('knowledge.vaultSourceView.source', { title })}>
      <VaultCodeMirror
        ariaLabel={t('knowledge.vaultSourceView.source', { title })}
        markdown={markdown}
        extensions={[]}
        onSelectionChange={onSelectionChange}
      />
      <dl className="dn-vault-source-status" aria-label={t('knowledge.vaultSourceView.metadata')}>
        <div><dt>{t('knowledge.vaultSourceView.path')}</dt><dd>{file.relative_path}</dd></div>
        <div><dt>{t('knowledge.vaultSourceView.format')}</dt><dd>{file.format}</dd></div>
        <div><dt>{t('knowledge.encoding')}</dt><dd>{metadataValue(file.encoding)}</dd></div>
        <div><dt>{t('knowledge.vaultSourceView.newline')}</dt><dd>{metadataValue(file.newline)}</dd></div>
        <div><dt>{t('knowledge.vaultSourceView.size')}</dt><dd>{t('knowledge.vaultSourceView.sizeBytes', { size: file.size_bytes })}</dd></div>
        <div><dt>{t('knowledge.vaultSourceView.hash')}</dt><dd>{file.content_hash?.slice(0, 12) || t('knowledge.vaultSourceView.unknown')}</dd></div>
      </dl>
    </section>
  )
}
