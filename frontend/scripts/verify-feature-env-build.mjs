import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = new URL('../tests/build-contract/.next-feature-contract/', import.meta.url)
const output = readFileSync(new URL('index.html', root), 'utf8')
const compact = output.replaceAll('<!-- -->', '').replace(/\s+/g, '')

const expected = [
  'evidence:true;',
  'visual:false;',
  'model:true;',
  'research:false',
]

for (const value of expected) {
  if (!compact.includes(value)) {
    throw new Error(`feature build contract missing generated value: ${value}`)
  }
}

function javascriptFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return javascriptFiles(path)
    return entry.name.endsWith('.js') ? [path] : []
  })
}

const chunks = javascriptFiles(
  fileURLToPath(new URL('_next/static/chunks/', root)),
).map(path =>
  readFileSync(path, 'utf8'),
)
const bundle = chunks.join('\n')

if (/process\.env\s*\[/.test(bundle)) {
  throw new Error('dynamic process.env lookup survived in the client bundle')
}

for (const name of [
  'NEXT_PUBLIC_DN_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_DN_VISUAL_REFRESH',
  'NEXT_PUBLIC_DN_MODEL_FLEET',
  'NEXT_PUBLIC_DN_RESEARCH_RUNS',
]) {
  if (bundle.includes(name)) {
    throw new Error(`public flag was not inlined by Next: ${name}`)
  }
}
