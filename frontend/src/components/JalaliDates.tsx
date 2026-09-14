/**
 * Jalali (Persian) date pickers built on react-multi-date-picker.
 *
 * Internal value contract: the rest of the app works with Gregorian
 * `YYYY-MM-DD` strings (and ISO datetimes); these components convert to
 * Jalali for display/input and back on change. Persian digits throughout.
 */
import { useMemo } from 'react'
import DatePicker, { DateObject } from 'react-multi-date-picker'
import TimePicker from 'react-multi-date-picker/plugins/time_picker'
import persian from 'react-date-object/calendars/persian'
import persian_fa from 'react-date-object/locales/persian_fa'
import gregorian from 'react-date-object/calendars/gregorian'
import gregorian_en from 'react-date-object/locales/gregorian_en'

const FA_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

function toFa(input: string | number): string {
  return String(input).replace(/\d/g, (d) => FA_DIGITS[Number(d)])
}

/** 'YYYY-MM-DD' (gregorian) → DateObject in persian calendar, or null */
function gregorianToDateObject(iso: string | null | undefined): DateObject | null {
  if (!iso) return null
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return null
  return new DateObject({
    year: Number(m[1]),
    month: Number(m[2]),
    day: Number(m[3]),
    calendar: gregorian,
    locale: gregorian_en,
  })
}

/** DateObject (any calendar) → gregorian 'YYYY-MM-DD' */
function dateObjectToGregorian(d: DateObject): string {
  const g = d.convert(gregorian, gregorian_en)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${g.year}-${p(g.month.number)}-${p(g.day)}`
}

const inputBase: React.CSSProperties = {
  width: '100%',
  height: 32,
  padding: '4px 11px',
  borderRadius: 6,
  fontFamily: 'inherit',
  fontSize: 14,
}

interface JalaliDatePickerProps {
  value: string | null // gregorian 'YYYY-MM-DD'
  onChange: (isoDate: string | null) => void
  placeholder?: string
  disabled?: boolean
  style?: React.CSSProperties
}

/** Date-only picker. Value is a Gregorian ISO date string. */
export function JalaliDatePicker({
  value,
  onChange,
  placeholder,
  disabled,
  style,
}: JalaliDatePickerProps) {
  const dateObj = useMemo(() => gregorianToDateObject(value), [value])
  return (
    <div style={style}>
      <DatePicker
        calendar={persian}
        locale={persian_fa}
        value={dateObj}
        disabled={disabled}
        placeholder={placeholder ?? 'انتخاب تاریخ'}
        onChange={(d) => {
          if (d == null) return onChange(null)
          const first = Array.isArray(d) ? d[0] : d
          if (first == null) return onChange(null)
          onChange(dateObjectToGregorian(first as DateObject))
        }}
        format="YYYY/MM/DD"
        editable={false}
        style={{ ...inputBase, direction: 'rtl', ...style }}
        calendarPosition="bottom-right"
      />
    </div>
  )
}

interface JalaliDateTimePickerProps {
  /** ISO datetime string with timezone, e.g. 2026-09-12T14:30:00+03:30 */
  value?: string | null
  onChange?: (isoDatetime: string) => void
  placeholder?: string
  disabled?: boolean
  style?: React.CSSProperties
}

/** Date + time picker (for appointment timestamps). Emits local ISO datetime
 * with the browser's timezone offset, which the API accepts as timestamptz. */
export function JalaliDateTimePicker({
  value,
  onChange,
  placeholder,
  disabled,
  style,
}: JalaliDateTimePickerProps) {
  const dateObj = useMemo(() => {
    if (!value) return null
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
    if (!m) return null
    const base = new DateObject({
      year: Number(m[1]),
      month: Number(m[2]),
      day: Number(m[3]),
      hour: Number(m[4]),
      minute: Number(m[5]),
      calendar: gregorian,
      locale: gregorian_en,
    })
    return base.convert(persian, persian_fa)
  }, [value])

  return (
    <div style={style}>
      <DatePicker
        calendar={persian}
        locale={persian_fa}
        value={dateObj}
        disabled={disabled}
        placeholder={placeholder ?? 'انتخاب تاریخ و ساعت'}
        onChange={(d) => {
          if (d == null) return
          const first = Array.isArray(d) ? d[0] : d
          if (first == null) return
          const obj = first as DateObject
          const g = obj.convert(gregorian, gregorian_en)
          const p = (n: number) => String(n).padStart(2, '0')
          const dt = new Date(
            `${g.year}-${p(g.month.number)}-${p(g.day)}T${p(obj.hour ?? 0)}:${p(
              obj.minute ?? 0,
            )}:00`,
          )
          const tz = -dt.getTimezoneOffset()
          const sign = tz >= 0 ? '+' : '-'
          const absTz = Math.abs(tz)
          const tzStr = `${sign}${p(Math.floor(absTz / 60))}:${p(absTz % 60)}`
          onChange?.(
            `${g.year}-${p(g.month.number)}-${p(g.day)}T${p(obj.hour ?? 0)}:${p(
              obj.minute ?? 0,
            )}:00${tzStr}`,
          )
        }}
        format="YYYY/MM/DD HH:mm"
        plugins={[<TimePicker key="tp" hideSeconds />]}
        editable={false}
        style={{ ...inputBase, direction: 'rtl', width: '100%', ...style }}
        calendarPosition="bottom-right"
      />
    </div>
  )
}

interface JalaliRangePickerProps {
  value: [string, string] // pair of gregorian 'YYYY-MM-DD'
  onChange: (range: [string, string]) => void
  disabled?: boolean
  style?: React.CSSProperties
}

/** Range picker for stats. Values are Gregorian ISO date strings. */
export function JalaliRangePicker({
  value,
  onChange,
  disabled,
  style,
}: JalaliRangePickerProps) {
  const dateObjs = useMemo(
    () => [gregorianToDateObject(value[0]), gregorianToDateObject(value[1])],
    [value],
  )
  return (
    <div style={style}>
      <DatePicker
        range
        calendar={persian}
        locale={persian_fa}
        value={dateObjs as DateObject[]}
        disabled={disabled}
        onChange={(d) => {
          if (d == null || Array.isArray(d) === false) return
          const arr = d as DateObject[]
          if (arr.length >= 2 && arr[0] && arr[1]) {
            onChange([dateObjectToGregorian(arr[0]), dateObjectToGregorian(arr[1])])
          }
        }}
        format="YYYY/MM/DD"
        editable={false}
        style={{ ...inputBase, direction: 'rtl', width: 'auto', ...style }}
        calendarPosition="bottom-right"
      />
    </div>
  )
}

export { toFa }
