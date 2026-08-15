import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(process.cwd(), 'src/lib/features.ts'), 'utf8')

const PUBLIC_FLAG_NAMES = [
  'NEXT_PUBLIC_DN_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_ONP_EVIDENCE_STUDIO',
  'NEXT_PUBLIC_DN_VISUAL_REFRESH',
  'NEXT_PUBLIC_ONP_VISUAL_REFRESH',
  'NEXT_PUBLIC_DN_MODEL_FLEET',
  'NEXT_PUBLIC_ONP_MODEL_FLEET',
  'NEXT_PUBLIC_DN_RESEARCH_RUNS',
  'NEXT_PUBLIC_ONP_RESEARCH_RUNS',
  'NEXT_PUBLIC_DN_STUDY_WORKBENCH',
  'NEXT_PUBLIC_DN_LUMINOUS_FOLIO',
  'NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2',
  'NEXT_PUBLIC_DN_SOURCE_VISUALS',
] as const

describe('Next production feature-flag contract', () => {
  it('uses a static process.env property reference for every public flag', () => {
    for (const name of PUBLIC_FLAG_NAMES) {
      expect(source).toContain(`process.env.${name}`)
    }
  })

  it('never uses dynamic process.env lookup for client feature flags', () => {
    expect(source).not.toMatch(/process\.env\s*\[/)
    expect(source).not.toMatch(/\b(?:const|let|var)\s+\w+\s*=\s*process\.env\b/)
  })

  it('does not introduce a legacy alias for the new Luminous Folio flag', () => {
    expect(source).not.toContain('NEXT_PUBLIC_ONP_LUMINOUS_FOLIO')
  })
})
