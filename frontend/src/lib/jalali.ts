// Jalali (Persian) calendar display helpers.

import dayjs from 'dayjs'
import jalaliday from 'jalaliday'

dayjs.extend(jalaliday)

const FA_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

export function toFaDigits(input: string | number): string {
  return String(input).replace(/\d/g, (d) => FA_DIGITS[Number(d)])
}

const FA_DIGITS_RE = /[۰-۹٠-٩]/g
const FA_TO_EN: Record<string, string> = {
  '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
  '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
  '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
  '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
}

/** Normalize Persian/Arabic digits to ASCII (inputs are typed with a Persian keyboard). */
export function toEnDigits(input: string): string {
  return input.replace(FA_DIGITS_RE, (d) => FA_TO_EN[d] ?? d)
}

export function formatJalali(iso: string, withTime = false): string {
  const d = dayjs(iso)
  const j = d.calendar('jalali').locale('fa')
  return withTime ? j.format('YYYY/MM/DD HH:mm') : j.format('YYYY/MM/DD')
}

export function formatJalaliTime(iso: string): string {
  const d = dayjs(iso)
  return d.calendar('jalali').locale('fa').format('HH:mm')
}

export function todayJalali(): string {
  return dayjs().calendar('jalali').locale('fa').format('YYYY/MM/DD')
}

/** Format a Gregorian ISO date (yyyy-mm-dd) as Jalali yyyy/mm/dd */
export function gregorianToJalali(isoDate: string): string {
  return dayjs(isoDate).calendar('jalali').locale('fa').format('YYYY/MM/DD')
}

/** Parse a Jalali yyyy/mm/dd input into a Gregorian ISO date (yyyy-mm-dd) */
export function jalaliToGregorian(jalali: string): string | null {
  const m = jalali.trim().match(/^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$/)
  if (!m) return null
  const [jy, jm, jd] = [Number(m[1]), Number(m[2]), Number(m[3])]
  if (jy < 1200 || jy > 1600 || jm < 1 || jm > 12 || jd < 1 || jd > 31) return null
  const g = dayjs()
    .calendar('jalali')
    .year(jy)
    .month(jm - 1)
    .date(jd)
  return g.format('YYYY-MM-DD')
}

export function formatMoney(amount: number): string {
  return toFaDigits(amount.toLocaleString('en-US'))
}

export function fileSize(bytes: number | null): string {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${toFaDigits(bytes)} بایت`
  if (bytes < 1024 * 1024) return `${toFaDigits((bytes / 1024).toFixed(1))} کیلوبایت`
  return `${toFaDigits((bytes / 1024 / 1024).toFixed(1))} مگابایت`
}
