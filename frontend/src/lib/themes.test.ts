import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { DEFAULT_THEME, THEMES, algorithmFor, getTheme } from './themes'

// the static CSS side that actually declares the palette custom properties
// (vitest always runs from frontend/, so cwd-based resolution is stable)
const cssSource = readFileSync(join(process.cwd(), 'src', 'index.css'), 'utf8')

describe('vibefarsi palettes', () => {
  it('exposes the six curated themes with a unique id each', () => {
    expect(THEMES.map((t) => t.id)).toEqual([
      'graphite',
      'turquoise',
      'saffron',
      'pomegranate',
      'lapis',
      'paper',
    ])
  })

  it('defaults to graphite and falls back to it on unknown ids', () => {
    expect(DEFAULT_THEME).toBe('graphite')
    expect(getTheme('graphite').id).toBe('graphite')
    expect(getTheme('nonexistent')).toBe(THEMES[0])
    expect(getTheme(null)).toBe(THEMES[0])
  })

  it('has exactly one light scheme (paper) and defaults to dark', () => {
    expect(THEMES.filter((t) => t.scheme === 'light').map((t) => t.id)).toEqual(['paper'])
    expect(getTheme(DEFAULT_THEME).scheme).toBe('dark')
  })

  it('carries a complete oklch CSS variable set per palette', () => {
    const required = [
      '--background',
      '--foreground',
      '--card',
      '--popover',
      '--primary',
      '--primary-foreground',
      '--muted-foreground',
      '--destructive',
      '--success',
      '--warning',
      '--border',
      '--input',
      '--ring',
      '--brand',
    ]
    for (const t of THEMES) {
      for (const key of required) {
        expect(t.cssVars[key], `${t.id} ${key}`).toMatch(/^oklch\(/)
      }
      expect(t.cssVars['--radius'], `${t.id} radius`).toMatch(/^[\d.]+rem$/)
    }
  })

  it('uses hex colors for antd tokens (tinycolor cannot parse oklch)', () => {
    const hexFields = ['background', 'foreground', 'card', 'popover', 'primary'] as const
    for (const t of THEMES) {
      expect(/^#[0-9a-f]{6}$/i.test(t.seed.colorPrimary as string), `${t.id} primary`).toBe(true)
      for (const f of hexFields) {
        expect(/^#[0-9a-f]{6}$/i.test(t.map[f === 'background' ? 'colorBgLayout' : 'colorBgContainer'] ?? ''), `${t.id} ${f}`).toBe(true)
      }
      // alpha colors (borders) stay rgba
      expect(t.map.colorBorder).toMatch(/^rgba\(/)
      expect(t.map.colorBorderSecondary).toMatch(/^rgba\(/)
    }
  })

  it('pairs a text-on-solid color with the primary (light primary → dark text)', () => {
    for (const t of THEMES) {
      const primary = t.seed.colorPrimary as string
      const solid = t.map.colorTextLightSolid
      // the pair must differ strongly: crude luminance check via hex distance
      const dist = (a: string, b: string) => {
        const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
        const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
        return pa.reduce((acc, v, i) => acc + Math.abs(v - pb[i]), 0)
      }
      expect(dist(primary, solid), `${t.id} primary/text-on-solid contrast`).toBeGreaterThan(150)
    }
  })

  it('keeps cssVars in sync with the static index.css blocks (the CSS side is what actually applies them)', () => {
    for (const t of THEMES) {
      for (const [key, value] of Object.entries(t.cssVars)) {
        expect(cssSource, `${t.id} ${key}: ${value}`).toContain(`${key}: ${value}`)
      }
    }
  })

  it('builds an antd algorithm that applies the palette map over the base derivation', () => {
    const paper = getTheme('paper')
    const algo = algorithmFor(paper)
    const fakeSeed = { colorPrimary: '#000000' } as unknown as Parameters<typeof algo>[0]
    const result = algo(fakeSeed) as unknown as Record<string, string>
    expect(result.colorBgLayout).toBe(paper.map.colorBgLayout)
    expect(result.colorTextLightSolid).toBe(paper.map.colorTextLightSolid)
  })
})
