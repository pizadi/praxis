import { useState } from 'react'
import { App as AntApp, Button } from 'antd'
import { CheckOutlined, CopyOutlined } from '@ant-design/icons'
import { theme as antdTheme } from 'antd'

import { toEnDigits } from '../lib/jalali'
import { copyText } from '../lib/clipboard'
import FaNumber from './FaNumber'

/** A FaNumber with a one-click copy button next to it (used for national ID
 * and phone number): the button copies the ASCII form — exactly what a
 * hand-selection copies via FaNumber's copy hook, minus the fiddliness.
 * Success is confirmed by a transient check on the button itself (no toast
 * spam when several fields are copied in a row). */
export default function CopyNumber({
  value,
  title,
  ascii = false,
}: {
  value: string | number | null | undefined
  title?: string
  /** Render ASCII digits instead of Persian (national IDs, phone numbers). */
  ascii?: boolean
}) {
  const { message } = AntApp.useApp()
  const { token } = antdTheme.useToken()
  const [copied, setCopied] = useState(false)
  if (value === null || value === undefined || value === '') return null

  const copy = async (): Promise<void> => {
    const ok = await copyText(toEnDigits(String(value)))
    if (ok) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } else {
      message.error('کپی نشد')
    }
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
      <FaNumber value={value} title={title} ascii={ascii} />
      <Button
        type="text"
        size="small"
        aria-label="کپی"
        title="کپی"
        icon={
          copied ? (
            <CheckOutlined style={{ color: token.colorSuccess }} />
          ) : (
            <CopyOutlined />
          )
        }
        onClick={(e) => {
          e.stopPropagation() // table rows: copying must not select/navigate
          void copy()
        }}
      />
    </span>
  )
}
