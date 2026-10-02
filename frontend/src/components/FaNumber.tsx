import type { CSSProperties, ReactElement } from 'react'
import { toEnDigits, toFaDigits } from '../lib/jalali'

/**
 * A number that READS as Persian digits but COPIES as ASCII digits.
 *
 * Persian users expect ۰۱۲۳۴۵۶۷۸۹ on screen, but pasting that into a bank
 * transfer form, a national-ID field or a search box that only accepts latin
 * script silently fails. There is no font feature (and no Vazirmatn variant)
 * that remaps ASCII digits to Persian glyphs, so the text itself IS Persian
 * (real, selectable, screen-reader friendly) and a document-level `copy`
 * hook rewrites the clipboard to ASCII whenever the selection intersects one
 * of these numbers.
 *
 * The hook lives on `document`, NOT on the number: a hand-dragged selection
 * almost always starts a few pixels outside the little span, and the copy
 * event then fires at an ancestor — a per-element onCopy would never see it.
 * Selections inside inputs/textareas (user-typed Persian digits) are not
 * touched: they never enter the document selection.
 *
 * For one-click copying, pair this with components/CopyNumber.tsx.
 *
 * Accepts anything numeric — including the already-Persian output of
 * `formatJalali`/`formatMoney`/`fileSize` (digits are normalized on the way
 * in, so a display helper can stay as it is).
 */

/** whether the current selection intersects any rendered .fa-num */
function selectionTouchesFaNum(sel: Selection): boolean {
  if (sel.rangeCount === 0) return false
  const range = sel.getRangeAt(0)
  for (const node of document.querySelectorAll('.fa-num')) {
    // intersectsNode, not containsNode: a hand-dragged selection usually
    // only PARTLY overlaps the little span (and jsdom's containsNode denies
    // even full containment of the container)
    if (range.intersectsNode(node)) return true
  }
  return false
}

let hookInstalled = false
function installCopyHook(): void {
  // window flag, not a module flag: Vite HMR re-evaluates this module and
  // would stack duplicate listeners across hot reloads
  if (hookInstalled || typeof document === 'undefined') return
  const w = window as unknown as Record<string, unknown>
  if (w.__faCopyHookInstalled) return
  w.__faCopyHookInstalled = true
  hookInstalled = true
  document.addEventListener('copy', (e) => {
    const sel = document.getSelection()
    // collapsed selection = a copy from within an input/textarea (those
    // selections never show up in the document selection) — leave it alone
    if (!sel || sel.isCollapsed || !selectionTouchesFaNum(sel)) return
    // read the SELECTION, not the clipboardData: Chromium hands you an empty
    // string from e.clipboardData.getData() inside a copy event, which made
    // this hook bail and the default (Persian) copy go through
    const text = sel.toString()
    if (!text) return
    e.preventDefault()
    e.clipboardData?.setData('text/plain', toEnDigits(text))
  })
}

export default function FaNumber({
  value,
  className,
  style,
  title,
  ascii = false,
}: {
  value: string | number | null | undefined
  className?: string
  style?: CSSProperties
  title?: string
  /** Render ASCII digits instead of Persian (national IDs, phone numbers —
   * read/copied as-is, no copy-hook translation needed). */
  ascii?: boolean
}): ReactElement | null {
  installCopyHook()
  if (value === null || value === undefined || value === '') return null
  const asciiText = toEnDigits(String(value))
  return (
    <span
      className={className ? `fa-num ${className}` : 'fa-num'}
      style={style}
      title={title}
      // explicit, not only in the stylesheet: a number must read LTR even if
      // the app dir flips, and the isolate keeps it out of the surrounding
      // bidi run (a stray number must not reorder the text around it)
      dir="ltr"
    >
      {ascii ? asciiText : toFaDigits(asciiText)}
    </span>
  )
}
