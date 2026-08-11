import { NextRequest } from 'next/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GET } from './route'

function request(
  url = 'http://notebook.example/config',
  headers: Record<string, string> = {},
): NextRequest {
  return new NextRequest(url, { headers })
}

async function body(response: Response): Promise<{ apiUrl: string }> {
  return response.json() as Promise<{ apiUrl: string }>
}

describe('runtime config route', () => {
  afterEach(() => {
    delete process.env.API_URL
    delete process.env.NEXT_PUBLIC_API_URL
    vi.restoreAllMocks()
  })

  it('keeps the explicit API_URL override as the first-priority JSON response', async () => {
    process.env.API_URL = 'https://configured.example:7443/api'

    const response = await GET(request('http://request.example/config', {
      host: 'attacker.example/path',
      'x-forwarded-proto': 'javascript',
    }))

    expect(response.status).toBe(200)
    expect(await body(response)).toEqual({ apiUrl: 'https://configured.example:7443/api' })
  })

  it('uses a valid forwarded HTTPS protocol and hostname', async () => {
    const response = await GET(request('http://request.example/config', {
      host: 'Notebook.Example:8443',
      'x-forwarded-proto': 'HTTPS',
    }))

    expect(await body(response)).toEqual({ apiUrl: 'https://notebook.example:5055' })
  })

  it('preserves bracketed IPv6 host syntax when adding the API port', async () => {
    const response = await GET(request('http://request.example/config', {
      host: '[2001:DB8::1]:8443',
      'x-forwarded-proto': 'https',
    }))

    expect(await body(response)).toEqual({ apiUrl: 'https://[2001:db8::1]:5055' })
  })

  it('accepts a standards-parsed IPv4 host', async () => {
    const response = await GET(request('http://request.example/config', {
      host: '192.0.2.44:3000',
      'x-forwarded-proto': 'http',
    }))

    expect(await body(response)).toEqual({ apiUrl: 'http://192.0.2.44:5055' })
  })

  it.each([
    ['javascript', 'safe.example'],
    ['ftp', 'safe.example'],
  ])('falls back safely for a non-HTTP(S) forwarded protocol (%s)', async (proto, host) => {
    const response = await GET(request('http://request.example/config', {
      host,
      'x-forwarded-proto': proto,
    }))

    expect(await body(response)).toEqual({ apiUrl: 'http://localhost:5055' })
  })

  it.each([
    'alice:secret@evil.example',
    'evil.example/private',
    'evil.example?next=https://alice:secret@evil.example',
    'evil.example#alice:secret@evil.example',
    '[2001:db8::1]/private',
  ])('falls back safely for a malformed or credential-bearing host (%s)', async (host) => {
    const response = await GET(request('http://request.example/config', {
      host,
      'x-forwarded-proto': 'https',
    }))

    const result = await body(response)
    expect(result).toEqual({ apiUrl: 'http://localhost:5055' })
    expect(JSON.stringify(result)).not.toMatch(/alice|secret|evil|private|javascript|ftp/)
  })

  it('does not trust a comma-separated or otherwise malformed forwarded protocol', async () => {
    const response = await GET(request('http://request.example/config', {
      host: 'safe.example',
      'x-forwarded-proto': 'https,http',
    }))

    expect(await body(response)).toEqual({ apiUrl: 'http://localhost:5055' })
  })

  it('falls back when the host header is missing', async () => {
    const response = await GET(request())

    expect(await body(response)).toEqual({ apiUrl: 'http://localhost:5055' })
  })
})
