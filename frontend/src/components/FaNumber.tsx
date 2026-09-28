import type { ClipboardEvent as ReactClipboardEvent, CSSProperties, ReactElement } from 'react'
import { toEnDigits, toFaDigits } from '../lib/jalali'

/**
 * A number that READS as Persian digits but COPIES as ASCII digits.
 *
 * Persian users expect ۰۱۲۳۴۵۶۷۸۹ on screen, but pasting that into a bank
 * transfer form, a national-ID field or a search box that only accepts latin
 * script silently fails. There is no font feature (and no Vazirmatn variant)
 * that remaps ASCII digits to Persian glyphs, so the text itself IS Persian
 * (real, selectable, screen-reader friendly) and a `copy` listener rewrites
 * the clipboard to ASCII as the selection leaves the element. Selection is a
 * plain text selection again — the earlier transparent-ASCII-underlayer hack
 * made the visible digits themselves unselectable.
 *
 * For one-click copying, pair this with components/CopyNumber.tsx.
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
  const onCopy = (e: ReactClipboardEvent<HTMLSpanElement>): void => {
    // whatever got selected (possibly mixed with surrounding text), hand the
    // clipboard the ASCII form — only Persian digit characters change
    const text = e.clipboardData.getData('text/plain')
    if (!text) return
    e.preventDefault()
    e.clipboardData.setData('text/plain', toEnDigits(text))
  }
  return (
    <span
      className={className ? `fa-num ${className}` : 'fa-num'}
      style={style}
      title={title}
      onCopy={onCopy}
      // explicit, not only in the stylesheet: a number must read LTR even if
      // the app dir flips, and the isolate keeps it out of the surrounding
      // bidi run (a stray number must not reorder the text around it)
      dir="ltr"
    >
      {toFaDigits(ascii)}
    </span>
  )
}
