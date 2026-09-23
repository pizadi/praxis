import { Grid } from 'antd'

import { useMemo } from 'react'

/** True below the antd `md` breakpoint (768px). Desktop-first: before the
 * first breakpoint event resolves it assumes a desktop shell so the layout
 * doesn't flash a mobile drawer on wide screens. */
export function useIsMobile(): boolean {
  const screens = Grid.useBreakpoint()
  return useMemo(() => !(screens.md ?? true), [screens])
}
