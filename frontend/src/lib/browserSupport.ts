/**
 * Browser-support floor. antd v5 generates its component styles at runtime
 * as `:where(...)`-wrapped CSS rules; engines older than Chrome/Edge 88
 * (2021) treat `:where` as an invalid selector and DROP every such rule —
 * sections of the UI silently collapse or vanish (reported: the patient
 * page's view lists on an older machine). Detect that class of engine once
 * at boot and warn loudly instead of failing silently.
 */

/** True when the engine understands the selectors antd v5 emits. */
export function browserSupported(): boolean {
  try {
    return (
      typeof CSS !== 'undefined' &&
      CSS.supports != null &&
      CSS.supports('selector(:where(*))')
    )
  } catch {
    return false
  }
}

/**
 * Prepend a plain-DOM banner (inline styles only — it must survive broken
 * antd styling on exactly the engines this targets). Once per session.
 */
export function warnUnsupportedBrowser(): void {
  if (browserSupported()) return
  try {
    if (sessionStorage.getItem('clinic.browser-warning') === '1') return
    sessionStorage.setItem('clinic.browser-warning', '1')
    const el = document.createElement('div')
    el.setAttribute('dir', 'rtl')
    el.style.cssText =
      'position:relative;z-index:9999;background:#fffbe6;color:#614700;' +
      'border-bottom:1px solid #ffe58f;padding:10px 16px;font-size:14px;' +
      'font-family:system-ui,sans-serif;text-align:center;line-height:1.8;'
    el.textContent =
      'نسخه مرورگر این دستگاه قدیمی است و صفحه ممکن است درست نمایش داده نشود — ' +
      'لطفاً Chrome یا Edge را به‌روزرسانی کنید (حداقل نسخه ۹۰).'
    document.body.prepend(el)
  } catch {
    // never block the app over the banner (privacy modes, odd engines)
  }
}
