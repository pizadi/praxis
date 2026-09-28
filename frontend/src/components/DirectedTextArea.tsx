import type { TextAreaProps } from 'antd/es/input'
import { Input } from 'antd'
import { textAlign, textDirection } from '../lib/textDir'

/**
 * A textarea whose direction follows its own content: Persian text aligns
 * right, a Latin/English note aligns left, and it re-decides on every
 * keystroke.
 *
 * rc-field-form controls this child (a Form.Item injects the live `value` and
 * `onChange`), so the direction is derived during render — the page is not
 * re-rendered per keystroke, and a value that arrives from outside the field
 * (switching appointment, a form reset) realigns immediately.
 */
export default function DirectedTextArea({ value, style, ...rest }: TextAreaProps) {
  const dir = textDirection(typeof value === 'string' ? value : undefined)
  return (
    <Input.TextArea
      {...rest}
      value={value}
      dir={dir}
      style={{ ...style, direction: dir, textAlign: textAlign(dir) }}
    />
  )
}
