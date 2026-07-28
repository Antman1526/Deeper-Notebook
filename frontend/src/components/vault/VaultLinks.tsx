import { Link2, Link2Off } from 'lucide-react'

import type { VaultLink } from '@/lib/api/vault'

export function VaultLinks({ title, links, direction, unresolvedLabel, onNavigate }: { title: string; links: VaultLink[]; direction: 'source' | 'target'; unresolvedLabel: string; onNavigate: (id: string) => void }) {
  return <section aria-labelledby={`${direction}-links-title`} className="space-y-2">
    <h2 id={`${direction}-links-title`} className="text-sm font-semibold">{title}</h2>
    {links.length ? <ul className="space-y-1" role="list">{links.map((link) => {
      const noteId = direction === 'source' ? link.source_note_id : link.target_note_id
      return <li key={link.id}>{noteId && link.resolved ? <button type="button" onClick={() => onNavigate(noteId)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Link2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />{link.alias || link.target_text}</button> : <span className="flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground"><Link2Off className="h-3.5 w-3.5" />{link.target_text} <span className="text-xs">{unresolvedLabel}</span></span>}</li>
    })}</ul> : <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">No links yet.</p>}
  </section>
}
