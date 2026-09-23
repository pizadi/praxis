import { theme as antdTheme } from 'antd'

/**
 * VibeFarsi palettes (https://vibefarsi.ir) adapted to the antd theme system.
 *
 * The palettes REPLACE the old light/dark toggle: each palette carries its own
 * color-scheme and «کاغذ» is the light option. Tokens are kept verbatim as
 * oklch CSS custom properties (applied on <html data-theme>) for hand-written
 * CSS (index.css), and additionally converted to hex/rgba for the antd
 * theme tokens (antd's tinycolor-based algorithms cannot parse oklch()).
 *
 * turquoise/saffron/pomegranate/lapis define no --destructive/--success/
 * --warning upstream — graphite's status colors are used there as a fallback.
 */

export type ThemeId =
  | 'graphite'
  | 'turquoise'
  | 'saffron'
  | 'pomegranate'
  | 'lapis'
  | 'paper'

export type Scheme = 'light' | 'dark'

export interface Palette {
  id: ThemeId
  label: string
  scheme: Scheme
  /** oklch CSS custom properties — the DECLARING side lives in index.css
   * (html[data-theme=…] blocks, first-paint); this mirror is kept in sync by
   * themes.test.ts and used nowhere at runtime */
  cssVars: Record<string, string>
  /** antd SEED tokens — set before the algorithm so hovers/disabled/fills derive well */
  seed: Record<string, string | number>
  /** antd MAP tokens — exact overrides applied AFTER the antd algorithm runs */
  map: Record<string, string>
}

const OKLCH_STATUS_FALLBACK = {
  '--destructive': 'oklch(0.65 0.2 25)',
  '--success': 'oklch(0.75 0.16 160)',
  '--warning': 'oklch(0.82 0.16 80)',
}

function palette(
  id: ThemeId,
  label: string,
  scheme: Scheme,
  vars: Record<string, string>,
  radiusPx: number,
  hex: {
    background: string; foreground: string; card: string; popover: string
    primary: string; primaryFg: string; mutedFg: string
    destructive: string; success: string; warning: string
    border: string; input: string; brand: string
  },
): Palette {
  return {
    id,
    label,
    scheme,
    cssVars: vars,
    seed: {
      colorPrimary: hex.primary,
      colorInfo: hex.primary,
      colorSuccess: hex.success,
      colorWarning: hex.warning,
      colorError: hex.destructive,
      colorBgBase: hex.background,
      colorTextBase: hex.foreground,
      colorLink: hex.brand,
      borderRadius: radiusPx,
    },
    map: {
      colorBgLayout: hex.background,
      colorBgContainer: hex.card,
      colorBgElevated: hex.popover,
      colorText: hex.foreground,
      colorTextSecondary: hex.mutedFg,
      colorTextTertiary: hex.mutedFg,
      colorTextQuaternary: hex.mutedFg,
      // text drawn on solid (primary/danger) fills — VibeFarsi primaries pair
      // a light fill with dark text (graphite) or the reverse (pomegranate)
      colorTextLightSolid: hex.primaryFg,
      colorBorderSecondary: hex.border,
      colorBorder: hex.input,
    },
  }
}

export const THEMES: Palette[] = [
  palette('graphite', 'گرافیت', 'dark', {
    '--background': 'oklch(0.115 0.002 285)',
    '--foreground': 'oklch(0.975 0 0)',
    '--card': 'oklch(0.14 0.002 285)',
    '--card-foreground': 'oklch(0.975 0 0)',
    '--popover': 'oklch(0.16 0.002 285)',
    '--popover-foreground': 'oklch(0.975 0 0)',
    '--primary': 'oklch(0.975 0 0)',
    '--primary-foreground': 'oklch(0.13 0 0)',
    '--secondary': 'oklch(0.2 0.002 285)',
    '--secondary-foreground': 'oklch(0.975 0 0)',
    '--muted': 'oklch(0.175 0.002 285)',
    '--muted-foreground': 'oklch(0.63 0.004 285)',
    '--accent': 'oklch(0.2 0.002 285)',
    '--accent-foreground': 'oklch(0.975 0 0)',
    '--destructive': 'oklch(0.65 0.2 25)',
    '--success': 'oklch(0.75 0.16 160)',
    '--warning': 'oklch(0.82 0.16 80)',
    '--border': 'oklch(1 0 0 / 8%)',
    '--input': 'oklch(1 0 0 / 11%)',
    '--ring': 'oklch(0.7 0 0)',
    '--brand': 'oklch(0.8 0.165 65)',
    '--brand-foreground': 'oklch(0.22 0.06 60)',
    '--radius': '0.625rem',
  }, 10, {
    background: '#050506', foreground: '#f7f7f7', card: '#09090a', popover: '#0d0d0e',
    primary: '#f7f7f7', primaryFg: '#070707', mutedFg: '#89898b',
    destructive: '#f14d4c', success: '#2acc8a', warning: '#fab72a',
    border: 'rgba(255, 255, 255, 0.08)', input: 'rgba(255, 255, 255, 0.11)', brand: '#ffa430',
  }),
  palette('turquoise', 'فیروزه', 'dark', {
    '--background': 'oklch(0.15 0.03 215)',
    '--foreground': 'oklch(0.97 0.01 200)',
    '--card': 'oklch(0.18 0.03 215)',
    '--card-foreground': 'oklch(0.97 0.01 200)',
    '--popover': 'oklch(0.2 0.03 215)',
    '--popover-foreground': 'oklch(0.97 0.01 200)',
    '--primary': 'oklch(0.83 0.13 190)',
    '--primary-foreground': 'oklch(0.16 0.04 200)',
    '--secondary': 'oklch(0.25 0.04 215)',
    '--secondary-foreground': 'oklch(0.97 0.01 200)',
    '--muted': 'oklch(0.22 0.035 215)',
    '--muted-foreground': 'oklch(0.72 0.04 205)',
    '--accent': 'oklch(0.25 0.04 215)',
    '--accent-foreground': 'oklch(0.97 0.01 200)',
    ...OKLCH_STATUS_FALLBACK,
    '--border': 'oklch(0.85 0.08 200 / 14%)',
    '--input': 'oklch(0.85 0.08 200 / 18%)',
    '--ring': 'oklch(0.83 0.13 190)',
    '--brand': 'oklch(0.88 0.1 185)',
    '--brand-foreground': 'oklch(0.16 0.04 200)',
    '--radius': '0.75rem',
  }, 12, {
    background: '#000e13', foreground: '#eef7f8', card: '#01151a', popover: '#04191e',
    primary: '#3fe2da', primaryFg: '#001214', mutedFg: '#88acb0',
    destructive: '#f14d4c', success: '#2acc8a', warning: '#fab72a',
    border: 'rgba(140, 222, 226, 0.14)', input: 'rgba(140, 222, 226, 0.18)', brand: '#85ede0',
  }),
  palette('saffron', 'زعفران', 'dark', {
    '--background': 'oklch(0.14 0.015 60)',
    '--foreground': 'oklch(0.97 0.01 80)',
    '--card': 'oklch(0.17 0.02 60)',
    '--card-foreground': 'oklch(0.97 0.01 80)',
    '--popover': 'oklch(0.19 0.02 60)',
    '--popover-foreground': 'oklch(0.97 0.01 80)',
    '--primary': 'oklch(0.8 0.15 75)',
    '--primary-foreground': 'oklch(0.2 0.05 70)',
    '--secondary': 'oklch(0.24 0.03 60)',
    '--secondary-foreground': 'oklch(0.97 0.01 80)',
    '--muted': 'oklch(0.21 0.025 60)',
    '--muted-foreground': 'oklch(0.72 0.04 70)',
    '--accent': 'oklch(0.24 0.03 60)',
    '--accent-foreground': 'oklch(0.97 0.01 80)',
    ...OKLCH_STATUS_FALLBACK,
    '--border': 'oklch(0.85 0.1 75 / 14%)',
    '--input': 'oklch(0.85 0.1 75 / 18%)',
    '--ring': 'oklch(0.8 0.15 75)',
    '--brand': 'oklch(0.86 0.14 85)',
    '--brand-foreground': 'oklch(0.2 0.05 70)',
    '--radius': '0.5rem',
  }, 8, {
    background: '#0e0804', foreground: '#f9f4ee', card: '#160d07', popover: '#1b120b',
    primary: '#f5ae39', primaryFg: '#241100', mutedFg: '#b5a18a',
    destructive: '#f14d4c', success: '#2acc8a', warning: '#fab72a',
    border: 'rgba(244, 197, 130, 0.14)', input: 'rgba(244, 197, 130, 0.18)', brand: '#fbc959',
  }),
  palette('pomegranate', 'انار', 'dark', {
    '--background': 'oklch(0.14 0.02 15)',
    '--foreground': 'oklch(0.97 0.01 15)',
    '--card': 'oklch(0.17 0.025 15)',
    '--card-foreground': 'oklch(0.97 0.01 15)',
    '--popover': 'oklch(0.19 0.025 15)',
    '--popover-foreground': 'oklch(0.97 0.01 15)',
    '--primary': 'oklch(0.7 0.18 20)',
    '--primary-foreground': 'oklch(0.98 0 0)',
    '--secondary': 'oklch(0.24 0.04 15)',
    '--secondary-foreground': 'oklch(0.97 0.01 15)',
    '--muted': 'oklch(0.21 0.03 15)',
    '--muted-foreground': 'oklch(0.72 0.04 15)',
    '--accent': 'oklch(0.24 0.04 15)',
    '--accent-foreground': 'oklch(0.97 0.01 15)',
    ...OKLCH_STATUS_FALLBACK,
    '--border': 'oklch(0.8 0.1 15 / 14%)',
    '--input': 'oklch(0.8 0.1 15 / 18%)',
    '--ring': 'oklch(0.7 0.18 20)',
    '--brand': 'oklch(0.8 0.12 25)',
    '--brand-foreground': 'oklch(0.2 0.05 20)',
    '--radius': '1rem',
  }, 16, {
    background: '#100607', foreground: '#fcf3f3', card: '#190b0c', popover: '#1e0f10',
    primary: '#fa676e', primaryFg: '#f8f8f8', mutedFg: '#bc9b9c',
    destructive: '#f14d4c', success: '#2acc8a', warning: '#fab72a',
    border: 'rgba(247, 163, 169, 0.14)', input: 'rgba(247, 163, 169, 0.18)', brand: '#ff9e96',
  }),
  palette('lapis', 'لاجورد', 'dark', {
    '--background': 'oklch(0.13 0.03 275)',
    '--foreground': 'oklch(0.97 0.01 275)',
    '--card': 'oklch(0.165 0.035 275)',
    '--card-foreground': 'oklch(0.97 0.01 275)',
    '--popover': 'oklch(0.19 0.035 275)',
    '--popover-foreground': 'oklch(0.97 0.01 275)',
    '--primary': 'oklch(0.7 0.16 275)',
    '--primary-foreground': 'oklch(0.98 0.01 275)',
    '--secondary': 'oklch(0.23 0.04 275)',
    '--secondary-foreground': 'oklch(0.97 0.01 275)',
    '--muted': 'oklch(0.2 0.035 275)',
    '--muted-foreground': 'oklch(0.72 0.04 275)',
    '--accent': 'oklch(0.23 0.04 275)',
    '--accent-foreground': 'oklch(0.97 0.01 275)',
    ...OKLCH_STATUS_FALLBACK,
    '--border': 'oklch(0.7 0.1 275 / 18%)',
    '--input': 'oklch(0.7 0.1 275 / 22%)',
    '--ring': 'oklch(0.7 0.16 275)',
    '--brand': 'oklch(0.8 0.12 255)',
    '--brand-foreground': 'oklch(0.16 0.04 265)',
    '--radius': '0.375rem',
  }, 6, {
    background: '#050613', foreground: '#f3f5fc', card: '#0a0d1d', popover: '#0f1223',
    primary: '#8393ff', primaryFg: '#f6f8ff', mutedFg: '#9da3be',
    destructive: '#f14d4c', success: '#2acc8a', warning: '#fab72a',
    border: 'rgba(140, 153, 221, 0.18)', input: 'rgba(140, 153, 221, 0.22)', brand: '#88c1ff',
  }),
  palette('paper', 'کاغذ', 'light', {
    '--background': 'oklch(0.985 0.004 85)',
    '--foreground': 'oklch(0.2 0.01 60)',
    '--card': 'oklch(1 0 0)',
    '--card-foreground': 'oklch(0.2 0.01 60)',
    '--popover': 'oklch(1 0 0)',
    '--popover-foreground': 'oklch(0.2 0.01 60)',
    '--primary': 'oklch(0.2 0.01 60)',
    '--primary-foreground': 'oklch(0.985 0.004 85)',
    '--secondary': 'oklch(0.94 0.008 85)',
    '--secondary-foreground': 'oklch(0.2 0.01 60)',
    '--muted': 'oklch(0.955 0.006 85)',
    '--muted-foreground': 'oklch(0.47 0.015 60)',
    '--accent': 'oklch(0.94 0.008 85)',
    '--accent-foreground': 'oklch(0.2 0.01 60)',
    '--destructive': 'oklch(0.58 0.2 25)',
    '--success': 'oklch(0.55 0.15 160)',
    '--warning': 'oklch(0.7 0.15 75)',
    '--border': 'oklch(0.2 0.01 60 / 12%)',
    '--input': 'oklch(0.2 0.01 60 / 16%)',
    '--ring': 'oklch(0.5 0.02 60)',
    '--brand': 'oklch(0.68 0.17 55)',
    '--brand-foreground': 'oklch(0.985 0 0)',
    '--radius': '0.75rem',
  }, 12, {
    background: '#fbfaf7', foreground: '#1a1512', card: '#ffffff', popover: '#ffffff',
    primary: '#1a1512', primaryFg: '#fbfaf7', mutedFg: '#615953',
    destructive: '#d73337', success: '#008b52', warning: '#d48e00',
    border: 'rgba(26, 21, 18, 0.12)', input: 'rgba(26, 21, 18, 0.16)', brand: '#e57600',
  }),
]

export const DEFAULT_THEME: ThemeId = 'graphite'

export function getTheme(id: string | null | undefined): Palette {
  return THEMES.find((t) => t.id === id) ?? THEMES[0]
}

type AntdAlgorithm = typeof antdTheme.darkAlgorithm

/** Builds the antd algorithm for a palette: the base light/dark algorithm
 * derives hover/disabled/fill states, then the palette's exact map tokens
 * (surfaces, text, borders) win over the derived values. */
export function algorithmFor(p: Palette): AntdAlgorithm {
  const base = p.scheme === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm
  return (seed) => ({ ...base(seed), ...p.map })
}
