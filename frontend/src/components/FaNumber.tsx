import type { CSSProperties, ReactElement } from 'react'
import { toEnDigits, toFaDigits } from '../lib/jalali'

/**
 * A number that READS as Persian digits but COPIES as ASCII digits.
 *
 * Persian users expect ۰۱۲۳۴۵۶۷۸۹ on screen, but pasting that into a bank
 * transfer form, a national-ID field or a search box that only accepts latin
 * script silently fails. There is no font feature (and no Vazirmatn variant)
 * that remaps ASCII digits to Persian glyphs, and rendering Persian digits as
 * the real text makes them uncopyable — so the two are layered instead:
 *
 *   .fa-num-src   the ASCII text, `color: transparent` — it still occupies
 *                 space, takes clicks and is what a selection copies
 *   .fa-num-fa    the Persian digits, absolutely positioned over it with
 *                 `user-select: none` so a selection never picks it up
 *
 * The result: the eye sees Persian digits, the clipboard gets ASCII, and
 * screen readers announce the ASCII form. Selection highlight lands on the
 * invisible layer, which is what the reader expects anyway.
 *
 * Accepts anything numeric — including the already-Persian output of
 * `formatJalali`/`formatMoney`/`fileSize` (digits are normalized on the way
 * in, so a display helper can stay as it is).
 */
export default function FaNumber({
  value,
  className,
  style,
  title,
}: {
  value: string | number | null | undefined
  className?: string
  style?: CSSProperties
  title?: string
}): ReactElement | null {
  if (value === null || value === undefined || value === '') return null
  const ascii = toEnDigits(String(value))
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
      <span className="fa-num-src">{ascii}</span>
      <span className="fa-num-fa" aria-hidden="true">
        {toFaDigits(ascii)}
      </span>
    </span>
  )
}
