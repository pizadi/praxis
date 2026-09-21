// jsdom shims needed by antd/rc-* + jest-dom matchers
import '@testing-library/jest-dom/vitest'

// antd's responsive helpers call window.matchMedia (absent in jsdom)
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

// rc-resize-observer (antd inputs) needs ResizeObserver
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

// user-event clicks need PointerEvent (missing in some jsdom builds)
if (typeof window.PointerEvent === 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).PointerEvent = class MouseEvent2 extends MouseEvent {
    constructor(type: string, params: Record<string, unknown> = {}) {
      super(type, params as never)
      Object.assign(this, { pointerId: params.pointerId ?? 1, pointerType: params.pointerType ?? 'mouse' })
    }
  }
  ;(window as any).Element.prototype.setPointerCapture ??= () => {}
  ;(window as any).Element.prototype.releasePointerCapture ??= () => {}
}
