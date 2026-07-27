import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  deeperNotebookFetch,
  onpFetch as canonicalCompatibilityExport,
} from './deeper-notebook'
import {
  deeperNotebookFetch as shimCanonicalExport,
  onpFetch as legacyModuleExport,
} from './onp'

describe('deeperNotebookFetch compatibility', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('keeps deprecated exports as aliases of the canonical helper', () => {
    expect(canonicalCompatibilityExport).toBe(deeperNotebookFetch)
    expect(shimCanonicalExport).toBe(deeperNotebookFetch)
    expect(legacyModuleExport).toBe(deeperNotebookFetch)
  })

  it('preserves auth-aware fetch behavior on canonical endpoints', async () => {
    localStorage.setItem(
      'auth-storage',
      JSON.stringify({ state: { token: 'owner-token' } }),
    )
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await deeperNotebookFetch('/api/deeper-notebook/theme')

    const [, init] = fetchMock.mock.calls[0]
    expect(new Headers(init.headers).get('Authorization')).toBe(
      'Bearer owner-token',
    )
  })
})
