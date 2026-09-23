import type { ReactNode } from 'react'
import { Typography } from 'antd'

/** Mobile-friendly stacked table cell: a primary line plus secondary lines
 * underneath — double/triple-height rows instead of horizontal scrolling.
 * Falsy lines are dropped. */
export default function StackCell({ main, lines }: { main: ReactNode; lines: ReactNode[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingBlock: 2, minWidth: 0 }}>
      <div>{main}</div>
      {lines.filter((l) => l !== null && l !== undefined && l !== '').map((line, i) => (
        <Typography.Text key={i} type="secondary" style={{ fontSize: 12 }}>
          {line}
        </Typography.Text>
      ))}
    </div>
  )
}
