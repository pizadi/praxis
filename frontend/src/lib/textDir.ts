// Text direction detection for free-text fields.
//
// The clinical note fields (CC/HX/PX) are mostly Persian, but doctors also
// paste drug names, lab values and English abbreviations — and a textarea
// locked to RTL mangles those. So the alignment follows the CONTENT: the first
// alphabetic character decides. Digits, punctuation and whitespace are
// skipped ("1403/05/12 — بیمار" is decided by the ب), and text with no letters
// at all keeps the app default (RTL).

/** Scripts written right-to-left that we treat as RTL. */
const RTL_LETTER =
  /[\p{Script=Arabic}\p{Script=Hebrew}\p{Script=Syriac}\p{Script=Thaana}\u200F\u200E]/u
const LETTER = /\p{L}/u

/**
 * 'rtl' when the first alphabetic character is from an RTL script, else 'ltr'.
 * Text without any letter → 'rtl' (the app-wide default).
 */
export function textDirection(text: string | null | undefined): 'rtl' | 'ltr' {
  if (!text) return 'rtl'
  for (const ch of text) {
    // code-point iteration, so a surrogate pair is tested as one character
    if (!LETTER.test(ch)) continue
    return RTL_LETTER.test(ch) ? 'rtl' : 'ltr'
  }
  return 'rtl'
}

/** Matching text-align for a direction (the textarea's alignment must follow). */
export function textAlign(direction: 'rtl' | 'ltr'): 'right' | 'left' {
  return direction === 'rtl' ? 'right' : 'left'
}
