import { NextRequest, NextResponse } from 'next/server'

const FALLBACK_API_URL = 'http://localhost:5055'

function normalizeHttpProtocol(value: string | null): 'http' | 'https' | null {
  const normalized = value?.trim().toLowerCase()
  return normalized === 'http' || normalized === 'https' ? normalized : null
}

/**
 * Parse only the authority portion accepted by a Host header. URL's parser
 * handles ports, DNS names, IPv4, and bracketed IPv6 without the lossy
 * `split(':')` behavior this endpoint previously used. Paths, credentials,
 * query strings, and fragments are not valid host values and fail closed.
 */
function parseHostHeader(hostHeader: string): string | null {
  const value = hostHeader.trim()
  if (!value || value !== hostHeader || /[/?#]/.test(value)) return null

  try {
    const parsed = new URL(`http://${value}`)
    if (
      parsed.username ||
      parsed.password ||
      parsed.pathname !== '/' ||
      parsed.search ||
      parsed.hash ||
      !parsed.hostname
    ) {
      return null
    }

    // URL.hostname is bracketed for IPv6 in the WHATWG implementation used by
    // Next.js. Keep the guard for runtimes that return the raw colon form.
    return parsed.hostname.includes(':') && !parsed.hostname.startsWith('[')
      ? `[${parsed.hostname}]`
      : parsed.hostname
  } catch {
    return null
  }
}

/**
 * Runtime Configuration Endpoint
 *
 * This endpoint provides server-side environment variables to the client at runtime.
 * This solves the NEXT_PUBLIC_* limitation where variables are baked into the build.
 *
 * Environment Variables:
 * - API_URL: Where the browser/client should make API requests (public/external URL)
 * - INTERNAL_API_URL: Where Next.js server-side should proxy API requests (internal URL)
 *   Default: http://localhost:5055 (used by Next.js rewrites in next.config.ts)
 *
 * Why two different variables?
 * - API_URL: Used by browser clients, can be https://your-domain.com or http://server-ip:5055
 * - INTERNAL_API_URL: Used by Next.js rewrites for server-side proxying, typically http://localhost:5055
 *
 * Auto-detection logic for API_URL:
 * 1. If API_URL env var is set, use it (explicit override)
 * 2. Otherwise, detect from incoming HTTP request headers (zero-config)
 * 3. Fallback to localhost:5055 if detection fails
 *
 * This allows the same Docker image to work in different deployment scenarios.
 */
export async function GET(request: NextRequest) {
  // Priority 1: Check if API_URL is explicitly set
  const envApiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL

  if (envApiUrl) {
    return NextResponse.json({
      apiUrl: envApiUrl,
    })
  }

  // Priority 2: Auto-detect from request headers
  try {
    // Check X-Forwarded-Proto first (for reverse proxies), but accept only
    // the two schemes this browser-facing endpoint can safely emit. An
    // explicitly malformed forwarded value falls back to localhost rather
    // than being replaced with an untrusted request/header value.
    const forwardedProto = request.headers.get('x-forwarded-proto')
    const proto = forwardedProto === null
      ? normalizeHttpProtocol(request.nextUrl.protocol.replace(/:$/, ''))
      : normalizeHttpProtocol(forwardedProto)

    // Get the host header (includes port if non-standard)
    const hostHeader = request.headers.get('host')

    if (proto && hostHeader) {
      const hostname = parseHostHeader(hostHeader)

      if (hostname) {
        // Construct the API URL with port 5055. `hostname` is already a
        // standards-parsed authority, including brackets for IPv6.
        const apiUrl = `${proto}://${hostname}:5055`

        return NextResponse.json({ apiUrl })
      }
    }
  } catch {
    // Preserve the safe fallback for malformed request implementations or
    // unexpected header values without reflecting raw input into logs/output.
  }

  // Priority 3: Fallback to localhost
  return NextResponse.json({ apiUrl: FALLBACK_API_URL })
}
