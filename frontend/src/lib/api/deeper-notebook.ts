/**
 * Auth-aware fetch for Deeper Notebook product-owned endpoints.
 *
 * The product components historically used raw fetch calls. That
 * works in the desktop bundle (which leaves OPEN_NOTEBOOK_PASSWORD unset and
 * so PasswordAuthMiddleware no-ops), but breaks in any deployment that sets
 * a password — every onp/* call returns 401 because the request has no
 * Authorization header.
 *
 * `deeperNotebookFetch` wraps the native fetch with two small additions:
 *   1. Pulls the auth token from the same `auth-storage` localStorage key
 *      that `apiClient` (axios) uses, so login state stays in sync.
 *   2. If the response is 401, clears auth state + redirects to /login —
 *      mirrors apiClient's response interceptor.
 *
 * Kept tiny on purpose. The components keep their own response
 * handling (varying error shapes, optimistic UI rollback, etc.) so we
 * deliberately don't migrate them to axios.
 */

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem('auth-storage')
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as { state?: { token?: string } }
    return parsed.state?.token ?? null
  } catch {
    return null
  }
}

export async function deeperNotebookFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = getAuthToken()
  const headers = new Headers(init.headers || {})
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(input, { ...init, headers })
  if (response.status === 401 && typeof window !== 'undefined') {
    // Match apiClient's behavior: blow away the bad token + bounce to login.
    // v0.6.20 — also skip the redirect if we're already on /login, to
    // match apiClient.ts and avoid a /login → /login bounce loop.
    localStorage.removeItem('auth-storage')
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  }
  return response
}

/** @deprecated Use deeperNotebookFetch. */
export const onpFetch = deeperNotebookFetch
