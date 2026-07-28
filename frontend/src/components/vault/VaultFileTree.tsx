'use client'

import { useMemo, useState } from 'react'
import { FileText, Search } from 'lucide-react'

import { Input } from '@/components/ui/input'
import type { VaultFile } from '@/lib/api/vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface VaultFileTreeProps { files: VaultFile[]; selectedNoteId: string; onSelect: (noteId: string) => void }

export function VaultFileTree({ files, selectedNoteId, onSelect }: VaultFileTreeProps) {
  const { t } = useTranslation()
  const [filter, setFilter] = useState('')
  const visible = useMemo(() => files.filter((file) => file.relative_path.toLocaleLowerCase().includes(filter.toLocaleLowerCase())), [files, filter])
  return <div className="flex min-h-0 flex-1 flex-col gap-3">
    <div className="relative"><Search aria-hidden className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input aria-label={t('knowledge.filterFiles')} value={filter} onChange={(event) => setFilter(event.target.value)} placeholder={t('knowledge.filterFiles')} className="pl-8" /></div>
    <div className="min-h-0 space-y-1 overflow-y-auto" role="tree" aria-label={t('knowledge.files')}>
      {visible.map((file) => { const noteId = file.note_id; return <button key={file.id} type="button" role="treeitem" aria-selected={selectedNoteId === noteId} onClick={() => onSelect(noteId)} className={cn('flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', selectedNoteId === noteId && 'bg-accent text-accent-foreground')}>
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" /><span className="min-w-0 flex-1 truncate">{file.relative_path}</span>{file.parse_status !== 'parsed' && <span className="text-xs text-muted-foreground">{file.parse_status}</span>}
      </button> })}
      {visible.length === 0 && <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground" role="status">{t('knowledge.noMatchingFiles')}</p>}
    </div>
  </div>
}
