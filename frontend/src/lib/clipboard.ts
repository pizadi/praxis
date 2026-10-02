/** Writes text to the clipboard: the async Clipboard API where available
 * (secure contexts — the app runs under HTTPS), falling back to a transient
 * textarea + execCommand for older/insecure setups. Resolves `false` when
 * both paths fail so callers can surface their own error. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // permission denied / insecure context — try the legacy path
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  } catch {
    return false
  }
}
