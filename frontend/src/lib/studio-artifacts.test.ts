import { describe, expect, it } from 'vitest'

import { artifactMarkdown, structuredArtifactMeta } from './studio-artifacts'

const structuredPayload = {
  schema_version: 1,
  document: {
    schema_version: 1,
    artifact_type: 'report',
    title: 'Report',
    sections: [],
  },
  markdown: '# Structured',
  content: '# Compatibility alias',
  validation: {
    status: 'valid',
    errors: [],
    strategy: 'native',
    attempts: 1,
  },
}

describe('Studio artifact envelopes', () => {
  it('reads existing legacy markdown content', () => {
    expect(artifactMarkdown({ content: '# Legacy' })).toBe('# Legacy')
  })

  it('prefers structured markdown and exposes validation state', () => {
    expect(artifactMarkdown(structuredPayload)).toBe('# Structured')
    expect(structuredArtifactMeta(structuredPayload)?.validation.status).toBe('valid')
    expect(structuredArtifactMeta(structuredPayload)?.validation.strategy).toBe('native')
  })

  it('falls back to content for future envelope versions', () => {
    expect(artifactMarkdown({
      ...structuredPayload,
      schema_version: 2,
      markdown: '# Future Markdown',
      content: '# Future Compatibility',
    })).toBe('# Future Compatibility')
  })

  it('falls back to content when the v1 document is malformed', () => {
    expect(artifactMarkdown({
      ...structuredPayload,
      document: { artifact_type: 'report' },
      markdown: '# Untrusted Markdown',
      content: '# Safe Compatibility',
    })).toBe('# Safe Compatibility')
    expect(structuredArtifactMeta({
      ...structuredPayload,
      document: { artifact_type: 'report' },
    })).toBeNull()
  })

  it('ignores non-string markdown and content values', () => {
    expect(artifactMarkdown({ markdown: {}, content: 42 })).toBe('')
  })
})
