import axios, { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { toast } from 'sonner'
import { getApiUrl } from '@/lib/config'

// v0.7.34 — central 5xx error surfacing.
//
// Before: only 401 was handled centrally. When the API hit 500 / 502 /
// 503 (worker dead, DB pool exhausted, local model provider down),
// each individual mutation had to surface its own toast — and several
// query hooks didn't, so silent failures sat on screen as stale data.
//
// Now: any 5xx triggers a toast at the interceptor level. Individual
// callers can opt out by setting `headers: { 'x-skip-error-toast': '1' }`
// on the request (useful for hooks that show their own inline error
// instead of a toast).
//
// Deduped so a flapping connection doesn't spam toasts: each unique
// (status, url) pair is rate-limited to once per 5 seconds.

interface ServerErrorKey {
  status: number
  url: string
}

const _recentServerErrorToasts = new Map<string, number>()
const _SERVER_ERROR_DEDUPE_MS = 5_000

function _shouldShowServerErrorToast(key: ServerErrorKey): boolean {
  const k = `${key.status}::${key.url}`
  const now = Date.now()
  const last = _recentServerErrorToasts.get(k) ?? 0
  if (now - last < _SERVER_ERROR_DEDUPE_MS) return false
  _recentServerErrorToasts.set(k, now)
  // Cheap GC — keep the map bounded.
  if (_recentServerErrorToasts.size > 64) {
    const cutoff = now - _SERVER_ERROR_DEDUPE_MS
    for (const [mk, mt] of _recentServerErrorToasts) {
      if (mt < cutoff) _recentServerErrorToasts.delete(mk)
    }
  }
  return true
}

// API client with runtime-configurable base URL
// The base URL is fetched from the API config endpoint on first request
// Timeout increased to 10 minutes (600000ms = 600s) to accommodate slow LLM operations
// (transformations, insights generation, chat) especially on slower hardware (Ollama, LM Studio)
// Note: Frontend uses milliseconds, backend uses seconds
// Local LLMs can take several minutes for complex questions with large contexts
export const apiClient = axios.create({
  timeout: 600000, // 600 seconds = 10 minutes
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: false,
})

// Request interceptor to add base URL and auth header
apiClient.interceptors.request.use(async (config) => {
  // Set the base URL dynamically from runtime config
  if (!config.baseURL) {
    const apiUrl = await getApiUrl()
    config.baseURL = `${apiUrl}/api`
  }

  if (typeof window !== 'undefined') {
    const authStorage = localStorage.getItem('auth-storage')
    if (authStorage) {
      try {
        const { state } = JSON.parse(authStorage)
        if (state?.token) {
          config.headers.Authorization = `Bearer ${state.token}`
        }
      } catch (error) {
        console.error('Error parsing auth storage:', error)
      }
    }
  }

  // Handle FormData vs JSON content types
  if (config.data instanceof FormData) {
    // Remove any Content-Type header to let browser set multipart boundary
    delete config.headers['Content-Type']
  } else if (config.method && ['post', 'put', 'patch'].includes(config.method.toLowerCase())) {
    config.headers['Content-Type'] = 'application/json'
  }

  return config
})

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    const status = error?.response?.status as number | undefined
    const config = error?.config as InternalAxiosRequestConfig | undefined
    const skipToast =
      config?.headers?.['x-skip-error-toast'] === '1' ||
      config?.headers?.['X-Skip-Error-Toast'] === '1'

    if (status === 401) {
      // Clear auth and redirect to login
      // v0.6.20 — skip the redirect if we're already on /login. Without
      // this guard, an authenticated API call that the login page itself
      // happens to make (e.g. checkAuth() racing against a fresh logout)
      // can spin the browser in /login → /login → /login forever.
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth-storage')
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      }
    } else if (status && status >= 500 && status < 600 && !skipToast) {
      // v0.7.34 — surface 5xx server failures at the interceptor so
      // every hook doesn't have to reinvent its own toast. Dedupes
      // by (status, url) within a 5s window so a flapping API
      // doesn't spam 50 toasts.
      const url = config?.url ?? '<unknown>'
      if (_shouldShowServerErrorToast({ status, url })) {
        const message =
          status === 503
            ? 'Service unavailable. The API or one of its dependencies is down.'
            : status === 502
              ? 'Bad gateway. The local model or downstream service is unreachable.'
              : 'Server error. Check the API log (~/.open-notebook-plus/logs/api.log) for details.'
        toast.error(message)
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient