import type { VaultPage } from '@/lib/api/vault'
import type { HeadingDescriptor, MarkdownModel } from '@/lib/vault/markdown-model'

interface VaultNoteSidebarProps {
  model: MarkdownModel
  page: VaultPage
  onHeading: (heading: HeadingDescriptor) => void
}

const propertyOutputLimit = 2_000

class BoundedOutput {
  private parts: string[] = []
  private length = 0
  stopped = false

  get remaining(): number {
    return propertyOutputLimit - this.length
  }

  append(value: string): boolean {
    if (this.stopped || this.remaining <= 0) {
      this.stopped = true
      return false
    }
    if (value.length <= this.remaining) {
      this.parts.push(value)
      this.length += value.length
      return true
    }
    const available = this.remaining
    this.parts.push(available === 1 ? '…' : `${value.slice(0, available - 1)}…`)
    this.length += available
    this.stopped = true
    return false
  }

  truncate(): void {
    if (this.remaining > 0) this.append('…')
    this.stopped = true
  }

  toString(): string {
    return this.parts.join('')
  }
}

function appendQuoted(output: BoundedOutput, value: string): void {
  if (!output.append('"')) return
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index]
    const code = character.charCodeAt(0)
    const escaped = character === '"' || character === '\\'
      ? `\\${character}`
      : character === '\b'
        ? '\\b'
        : character === '\f'
          ? '\\f'
          : character === '\n'
            ? '\\n'
            : character === '\r'
              ? '\\r'
              : character === '\t'
                ? '\\t'
                : code < 0x20
                  ? `\\u${code.toString(16).padStart(4, '0')}`
                  : character
    if (escaped.length + 1 > output.remaining) {
      output.truncate()
      return
    }
    if (!output.append(escaped)) return
  }
  output.append('"')
}

function appendStructured(
  output: BoundedOutput,
  value: unknown,
  seen: Set<object>,
  depth: number,
): void {
  if (output.stopped) return
  if (value === null) {
    output.append('null')
    return
  }
  if (typeof value === 'string') {
    appendQuoted(output, value)
    return
  }
  if (typeof value === 'number') {
    output.append(Number.isFinite(value) ? String(value) : 'null')
    return
  }
  if (typeof value === 'boolean') {
    output.append(String(value))
    return
  }
  if (typeof value !== 'object') {
    appendQuoted(output, '[Unserializable]')
    return
  }
  if (seen.has(value)) {
    appendQuoted(output, '[Circular]')
    return
  }
  if (depth >= 20) {
    appendQuoted(output, '[Depth limit]')
    return
  }

  seen.add(value)
  if (Array.isArray(value)) {
    output.append('[')
    let length = 0
    try {
      length = value.length
    } catch {
      appendQuoted(output, '[Unserializable]')
    }
    for (let index = 0; index < length && !output.stopped; index += 1) {
      if (index > 0) output.append(',')
      try {
        appendStructured(output, value[index], seen, depth + 1)
      } catch {
        appendQuoted(output, '[Unserializable]')
      }
    }
    if (!output.stopped) output.append(']')
    seen.delete(value)
    return
  }

  output.append('{')
  let propertyIndex = 0
  try {
    for (const key in value as Record<string, unknown>) {
      if (!Object.prototype.hasOwnProperty.call(value, key)) continue
      if (propertyIndex > 0) output.append(',')
      appendQuoted(output, key)
      if (!output.append(':')) break
      try {
        appendStructured(output, (value as Record<string, unknown>)[key], seen, depth + 1)
      } catch {
        appendQuoted(output, '[Unserializable]')
      }
      propertyIndex += 1
      if (output.stopped) break
    }
  } catch {
    if (!output.stopped) {
      if (propertyIndex > 0) output.append(',')
      appendQuoted(output, '[Unserializable]')
      output.append(':null')
    }
  }
  if (!output.stopped) output.append('}')
  seen.delete(value)
}

function compareDisplay(left: string, right: string): number {
  const localized = left.localeCompare(right, 'en-US', { sensitivity: 'base' })
  if (localized !== 0) return localized
  return left === right ? 0 : left < right ? -1 : 1
}

function boundedScalar(value: unknown): string {
  try {
    const rendered = String(value)
    return rendered.length > propertyOutputLimit
      ? `${rendered.slice(0, propertyOutputLimit - 1)}…`
      : rendered
  } catch {
    return '[Unserializable]'
  }
}

function formatProperty(value: unknown): string {
  if (value === null || typeof value !== 'object') return boundedScalar(value)
  const output = new BoundedOutput()
  try {
    appendStructured(output, value, new Set<object>(), 0)
    return output.toString() || '[Unserializable]'
  } catch {
    return '[Unserializable]'
  }
}

export function VaultNoteSidebar({ model, page, onHeading }: VaultNoteSidebarProps) {
  const properties = Object.entries(page.note.properties || {})
    .sort(([left], [right]) => compareDisplay(left, right))
  const tags = Array.from(new Set(page.note.tags || [])).sort(compareDisplay)

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
            {tags.map((tag) => <li key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs">#{tag}</li>)}
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
