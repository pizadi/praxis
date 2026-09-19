// Route-level unsaved-changes guard: the layout's menu navigations are
// routed through navigateGuarded(); a mounted page (with unsaved-changes
// state of its own) registers a blocker that opens its confirm dialog.
import { createContext, useContext, useEffect } from 'react'

export interface NavBlocker {
  isDirty: () => boolean
  /** Called instead of navigating; the page opens its save/discard/stay
   * dialog and completes (or cancels) the navigation itself. */
  requestLeave: (to: string) => void
}

export const NavGuardCtx = createContext<{
  registerNavBlocker: (b: NavBlocker | null) => void
  navigateGuarded: (to: string) => void
}>({
  registerNavBlocker: () => {},
  navigateGuarded: () => {},
})

export function useNavGuard() {
  return useContext(NavGuardCtx)
}

/** Browser-level guard: native «leave site?» dialog on tab close/refresh
 * while dirty (the message text is browser-controlled by spec). */
export function useBeforeUnloadGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])
}
