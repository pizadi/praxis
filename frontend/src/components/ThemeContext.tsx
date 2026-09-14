import { createContext, useContext, useEffect, useState } from 'react'
import { theme as antdTheme } from 'antd'

export type ThemeMode = 'light' | 'dark'

export interface ThemeCtx {
  isDark: boolean
  toggle: () => void
}

export const ThemeContext = createContext<ThemeCtx>({
  isDark: false,
  toggle: () => {},
})

export function useTheme() {
  return useContext(ThemeContext)
}

const STORAGE_KEY = 'clinic-theme'

export function readStoredTheme(): ThemeMode {
  return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

/** Creates the provider value and keeps <html> class + localStorage in sync. */
export function useThemeState(): { ctx: ThemeCtx; algorithm: typeof antdTheme.defaultAlgorithm } {
  const [mode, setMode] = useState<ThemeMode>(readStoredTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', mode === 'dark')
    localStorage.setItem(STORAGE_KEY, mode)
  }, [mode])

  const ctx: ThemeCtx = {
    isDark: mode === 'dark',
    toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')),
  }
  return { ctx, algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm }
}
