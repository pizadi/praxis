import axios, { AxiosError } from 'axios'

export const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE,
})

// --- Token storage -----------------------------------------------------------

const ACCESS_KEY = 'clinic.access'
const REFRESH_KEY = 'clinic.refresh'
const USER_KEY = 'clinic.user'

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
  return localStorage.getItem(ACCESS_KEY)
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}
export function getStoredUser(): StoredUser | null {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? (JSON.parse(raw) as StoredUser) : null
}
export function setTokens(access: string, refresh: string, user: StoredUser) {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}
export function clearAuth() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

// --- Request/response interceptors -------------------------------------------

let refreshInFlight: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null
  try {
    const res = await axios.post(`${API_BASE}/auth/refresh`, {
      refresh_token: refresh,
    })
    const { access_token, refresh_token } = res.data
    localStorage.setItem(ACCESS_KEY, access_token)
    localStorage.setItem(REFRESH_KEY, refresh_token)
    return access_token
  } catch {
    clearAuth()
    return null
  }
}

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true
      refreshInFlight ??= tryRefresh().finally(() => {
        refreshInFlight = null
      })
      const token = await refreshInFlight
      if (token) {
        original.headers.set('Authorization', `Bearer ${token}`)
        return api(original)
      }
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
