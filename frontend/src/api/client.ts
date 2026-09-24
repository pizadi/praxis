import axios, { AxiosError } from 'axios'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
})

// The access token lives only in this module. The long-lived refresh token is
// an HttpOnly cookie managed by the API; localStorage keeps only non-secret
// user/permission display state.
let accessToken: string | null = null

const USER_KEY = 'clinic.user'
const LEGACY_ACCESS_KEY = 'clinic.access'
const LEGACY_REFRESH_KEY = 'clinic.refresh'
const CSRF_COOKIE = 'praxis_csrf'

// Remove credentials written by versions before the HttpOnly-cookie migration.
localStorage.removeItem(LEGACY_ACCESS_KEY)
localStorage.removeItem(LEGACY_REFRESH_KEY)

export interface StoredUser {
  id: number
  username: string
  full_name: string
  role_id: number
  role_name: string
  permissions: string[]
}

export function hasPerm(
  user: StoredUser | null,
  ...perms: string[]
): boolean {
  if (!user) return false
  const held = new Set(user.permissions ?? [])
  return perms.some((p) => held.has(p))
}

export function getAccessToken(): string | null {
  return accessToken
}

export function getStoredUser(): StoredUser | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as StoredUser
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export function setAuth(access: string, user: StoredUser) {
  accessToken = access
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

/** Refresh only the cached user (permissions change server-side between logins). */
export function storeUser(user: StoredUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  accessToken = null
  localStorage.removeItem(USER_KEY)
}

function csrfToken(): string {
  const prefix = `${CSRF_COOKIE}=`
  const part = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(prefix))
  return part ? decodeURIComponent(part.slice(prefix.length)) : ''
}

// --- Request/response interceptors -------------------------------------------

let refreshInFlight: Promise<string | null> | null = null

/** Coordinated refresh: concurrent callers share one in-flight rotation. */
export async function ensureAccessToken(): Promise<string | null> {
  return refreshOnce()
}

async function refreshAccessToken(): Promise<string | null> {
  const csrf = csrfToken()
  if (!csrf) return null
  try {
    const res = await axios.post(
      `${API_BASE}/auth/refresh`,
      undefined,
      {
        withCredentials: true,
        headers: { 'X-CSRF-Token': csrf },
      },
    )
    accessToken = res.data.access_token as string
    return accessToken
  } catch {
    return null
  }
}

function refreshOnce(): Promise<string | null> {
  refreshInFlight ??= refreshAccessToken().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  const csrf = csrfToken()
  if (csrf && config.url?.includes('/auth/')) {
    config.headers['X-CSRF-Token'] = csrf
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined
    const isAuthEndpoint = original?.url?.includes('/auth/login') ||
      original?.url?.includes('/auth/refresh') ||
      original?.url?.includes('/auth/logout')
    if (
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !isAuthEndpoint
    ) {
      original._retried = true
      const token = await refreshOnce()
      if (token) {
        original.headers.set('Authorization', `Bearer ${token}`)
        return api(original)
      }
      clearAuth()
      window.location.hash = '#/login'
    }
    return Promise.reject(error)
  },
)

// --- Error normalization --------------------------------------------------------

export interface ApiError {
  code: string
  message: string
  details?: unknown
}

export function apiError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { error?: ApiError } | undefined
    if (data?.error) return data.error
    if (err.response) {
      return { code: `http_${err.response.status}`, message: 'خطای سرور' }
    }
    return { code: 'network', message: 'خطای شبکه' }
  }
  return { code: 'unknown', message: 'خطای نامشخص' }
}

/** Per-field error messages from a 422 `invalid_answers`-style envelope
 * (`{"error": {"details": {"fields": {key: message}}}}`), if present. */
export function apiFieldErrors(err: unknown): Record<string, string[]> | undefined {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as
      | { error?: { details?: { fields?: Record<string, string> } } }
      | undefined
    const fields = data?.error?.details?.fields
    return fields
      ? Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, [v]]))
      : undefined
  }
  return undefined
}
