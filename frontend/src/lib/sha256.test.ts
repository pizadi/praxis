import { describe, expect, it } from 'vitest'

import { sha256File } from './sha256'

describe('sha256File (streaming)', () => {
  it('matches crypto.subtle on a multi-chunk payload', async () => {
    // > 2 chunks at a tiny slice size exercises the loop + boundaries
    const bytes = new Uint8Array(5000)
    for (let i = 0; i < bytes.length; i++) bytes[i] = i % 251
    const blob = new Blob([bytes])

    // ground truth straight from the raw bytes (no Blob API needed here)
    const expected = await crypto.subtle.digest('SHA-256', bytes)
    const expectedHex = Array.from(new Uint8Array(expected))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('')

    // tiny slices → the payload spans multiple chunks (loop + boundaries)
    expect(await sha256File(blob, undefined, 1024)).toBe(expectedHex)
  })

  it('reports progress 0..1 monotonically ending at 1', async () => {
    const blob = new Blob([new Uint8Array(3000)])
    const seen: number[] = []
    await sha256File(blob, (f) => seen.push(f), 1024)
    expect(seen.length).toBeGreaterThan(0)
    expect(seen[seen.length - 1]).toBe(1)
    for (let i = 1; i < seen.length; i++) expect(seen[i]).toBeGreaterThan(seen[i - 1])
  })

  it('handles an empty file', async () => {
    // SHA-256 of the empty string
    expect(await sha256File(new Blob([]))).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    )
  })
})
