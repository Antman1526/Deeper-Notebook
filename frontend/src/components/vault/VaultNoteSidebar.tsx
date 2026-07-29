import type { VaultPage } from '@/lib/api/vault'
import type { HeadingDescriptor, MarkdownModel } from '@/lib/vault/markdown-model'

interface VaultNoteSidebarProps {
  model: MarkdownModel
  page: VaultPage
  onHeading: (heading: HeadingDescriptor) => void
}

function compareDisplay(left: string, right: string): number {
  return left.localeCompare(right, undefined, { sensitivity: 'base' })
}

function formatProperty(value: unknown): string {
  const rendered = value !== null && typeof value === 'object'
    ? JSON.stringify(value)
    : String(value)
  return rendered.length > 2_000 ? `${rendered.slice(0, 1_999)}…` : rendered
}

export function VaultNoteSidebar({ model, page, onHeading }: VaultNoteSidebarProps) {
  const properties = Object.entries(page.note.properties || {})
    .sort(([left], [right]) => compareDisplay(left, right))
  const tags = [...(page.note.tags || [])].sort(compareDisplay)

  return (
    <aside className="space-y-5" aria-label="Note details">
      <section aria-labelledby="vault-outline-title">
        <h3 id="vault-outline-title" className="text-sm font-semibold">Outline</h3>
        {model.headings.length ? (
          <ol className="mt-2 space-y-1 text-sm text-muted-foreground">
            {model.headings.map((heading) => (
              <li key={`${heading.slug}-${heading.sourceFrom}`} className={heading.level > 1 ? 'pl-2' : undefined}>
                <button
                  type="button"
                  className="text-left hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={`Level ${heading.level} ${heading.text}`}
                  onClick={() => onHeading(heading)}
                >
                  {heading.text}
                </button>
              </li>
            ))}
          </ol>
        ) : <p className="mt-2 text-sm text-muted-foreground">No headings</p>}
      </section>

      <section aria-labelledby="vault-properties-title">
        <h3 id="vault-properties-title" className="text-sm font-semibold">Properties</h3>
        {properties.length ? (
          <dl className="mt-2 space-y-1 text-sm text-muted-foreground">
            {properties.map(([key, value]) => (
              <div key={key}>
                <dt className="font-medium text-foreground">{key}</dt>
                <dd>{formatProperty(value)}</dd>
              </div>
            ))}
          </dl>
        ) : <p className="mt-2 text-sm text-muted-foreground">No properties</p>}
      </section>

      <section aria-labelledby="vault-tags-title">
        <h3 id="vault-tags-title" className="text-sm font-semibold">Tags</h3>
        {tags.length ? (
          <ul className="mt-2 flex flex-wrap gap-1" role="list">
            {tags.map((tag) => <li key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">#{tag.toLocaleLowerCase('en-US')}</li>)}
          </ul>
        ) : <p className="mt-2 text-sm text-muted-foreground">No tags</p>}
      </section>

      <section aria-labelledby="vault-source-title">
        <h3 id="vault-source-title" className="text-sm font-semibold">Source</h3>
        <p className="mt-2 break-all text-sm text-muted-foreground">{page.file.relative_path}</p>
      </section>
    </aside>
  )
}
