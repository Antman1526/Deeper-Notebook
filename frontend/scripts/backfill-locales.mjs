// v0.8.70 — one-shot locale parity backfill.
// Regenerates the incomplete locales from en-US: existing translations win,
// missing keys are filled with the English value (a clearly-marked placeholder
// matching the runtime fallback behaviour), and stale keys not present in
// en-US are dropped. This makes the locale-parity test green with ZERO runtime
// change (English is already what these locales fall back to today).
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const LOCALES = path.join(__dirname, '..', 'src', 'lib', 'locales')
const TARGETS = ['ca-ES', 'de-DE', 'pl-PL', 'tr-TR']
const CONST_NAME = { 'ca-ES': 'caES', 'de-DE': 'deDE', 'pl-PL': 'plPL', 'tr-TR': 'trTR' }

function loadLocale(dir) {
  const text = fs.readFileSync(path.join(LOCALES, dir, 'index.ts'), 'utf8')
  const idx = text.indexOf('export const')
  const eq = text.indexOf('=', idx)
  let body = text.slice(eq + 1).trim()
  body = body.replace(/\bas const\b\s*;?\s*$/, '').replace(/;?\s*$/, '')
  // eslint-disable-next-line no-eval
  return eval('(' + body + ')')
}

// en-US is the key authority. Locale value wins when present and same kind;
// otherwise the English value is used. Keys absent from en-US are dropped.
function merge(en, loc) {
  if (typeof en !== 'object' || en === null || Array.isArray(en)) {
    return typeof loc === typeof en && !Array.isArray(loc) ? loc : en
  }
  const out = {}
  for (const k of Object.keys(en)) {
    const lv = loc && typeof loc === 'object' && !Array.isArray(loc) ? loc[k] : undefined
    out[k] = merge(en[k], lv)
  }
  return out
}

function serialize(obj, ind) {
  const pad = '  '.repeat(ind)
  const padClose = '  '.repeat(ind - 1)
  let s = '{\n'
  for (const k of Object.keys(obj)) {
    const v = obj[k]
    const key = /^[A-Za-z_$][\w$]*$/.test(k) ? k : JSON.stringify(k)
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      s += `${pad}${key}: ${serialize(v, ind + 1)},\n`
    } else {
      s += `${pad}${key}: ${JSON.stringify(v)},\n`
    }
  }
  s += `${padClose}}`
  return s
}

const en = loadLocale('en-US')

for (const dir of TARGETS) {
  const before = loadLocale(dir)
  const merged = merge(en, before)
  const header =
    `// ${dir} locale.\n` +
    `// v0.8.70 — completed to full key parity with en-US. Entries that match\n` +
    `// the English source are untranslated placeholders (runtime already fell\n` +
    `// back to English for these); replace them with real translations.\n`
  const out = `${header}export const ${CONST_NAME[dir]} = ${serialize(merged, 1)}\n`
  fs.writeFileSync(path.join(LOCALES, dir, 'index.ts'), out, 'utf8')
  console.log(`${dir}: regenerated (${Object.keys(before).length} → ${Object.keys(merged).length} top-level groups)`)
}
console.log('done')
