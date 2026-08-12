const LOOPBACK_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1'])

export function isAllowedLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase().replace(/^\[|\]$/g, '')
  return LOOPBACK_HOSTNAMES.has(normalized)
}

export function isExternalRequest(requestUrl: string): boolean {
  try {
    return !isAllowedLoopbackHostname(new URL(requestUrl).hostname)
  } catch {
    return true
  }
}
