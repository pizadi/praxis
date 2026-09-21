import { Input } from 'antd'
import type { InputProps } from 'antd'

import { toEnDigits } from '../lib/jalali'

/** Text input that rewrites Persian/Arabic digits to ASCII as the user
 * types (Persian keyboards): the DB stores ASCII digits and digit-pattern
 * validation must see them. Use for numeric-as-text fields (national ID,
 * phone, year of birth, money amounts); for spinny number boxes
 * (antd InputNumber) normalize via `parser` instead. */
export default function DigitInput({ onChange, ...rest }: InputProps) {
  return (
    <Input
      {...rest}
      onChange={(e) => {
        e.target.value = toEnDigits(e.target.value)
        onChange?.(e)
      }}
    />
  )
}
