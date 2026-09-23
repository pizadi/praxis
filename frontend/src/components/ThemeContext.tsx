import { createContext, useContext, useEffect, useState } from 'react'

import { DEFAULT_THEME, getTheme, THEMES, type Palette, type ThemeId } from '../lib/themes'

export interface ThemeCtx {
  /** the active VibeFarsi palette */
  theme: Palette
  setTheme: (id: ThemeId) => void
  isDark: boolean
}

export const ThemeContext = createContext<ThemeCtx>({
  theme: THEMES[0],
  setTheme: () => {},
  isDark: true,
})

export function useTheme() {
  return useContext(ThemeContext)
}

/** Session-scoped (survives a refresh in this tab, resets on a new session). */
const STORAGE_KEY = 'clinic-theme-session'

export function readStoredTheme(): ThemeId {
  try {
    return getTheme(sessionStorage.getItem(STORAGE_KEY)).id
  } catch {
    return DEFAULT_THEME
  }
}

/**
 * Creates the provider value and keeps <html> (data-theme, dark class,
 * color-scheme) + sessionStorage in sync. `algorithm` feeds ConfigProvider —
 * see lib/themes.ts for how the palette maps onto antd tokens.
 */
export function useThemeState(): { ctx: ThemeCtx; palette: Palette } {
  const [themeId, setThemeId] = useState<ThemeId>(readStoredTheme)
  const palette = getTheme(themeId)

  useEffect(() => {
    const html = document.documentElement
    html.dataset.theme = palette.id
    html.classList.toggle('dark', palette.scheme === 'dark')
    html.style.colorScheme = palette.scheme
    try {
      sessionStorage.setItem(STORAGE_KEY, palette.id)
    } catch {
      // storage unavailable (privacy mode) — the choice just won't persist
    }
  }, [palette])

  const ctx: ThemeCtx = {
    theme: palette,
    setTheme: setThemeId,
    isDark: palette.scheme === 'dark',
  }
  return { ctx, palette }
}
