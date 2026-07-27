import { afterEach, describe, expect, it, vi } from 'vitest'

import { deeperNotebookFetch } from './deeper-notebook'

describe('deeperNotebookFetch', () => {
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
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
