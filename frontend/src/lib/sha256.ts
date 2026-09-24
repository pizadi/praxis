/**
 * Streaming SHA-256 for large files. crypto.subtle can only digest a whole
 * buffer in one shot — fine for attachments, but a multi-GB backup tarball
 * must NEVER be read into memory (f.arrayBuffer() would OOM the tab). This
 * hashes incrementally: fixed-size slices, each read one at a time.
 */
import { sha256 } from 'js-sha256'

const CHUNK_BYTES = 16 * 1024 * 1024 // 16 MiB slices

async function blobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  // browsers (Chrome ≥ 76) have Blob.arrayBuffer; jsdom's Blob polyfill
  // doesn't — FileReader works in both
  if (typeof blob.arrayBuffer === 'function') return blob.arrayBuffer()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
  })
}

/** Hex digest of a File/Blob, hashing chunk by chunk. onProgress reports
 * 0..1 after each chunk (hashing a huge tarball takes a while — show it).
 * chunkBytes is injectable for tests. */
export async function sha256File(
  file: Blob,
  onProgress?: (fraction: number) => void,
  chunkBytes: number = CHUNK_BYTES,
): Promise<string> {
  const hasher = sha256.create()
  for (let offset = 0; offset < file.size; offset += chunkBytes) {
    const slice = file.slice(offset, Math.min(offset + chunkBytes, file.size))
    hasher.update(await blobToArrayBuffer(slice))
    onProgress?.(Math.min(offset + chunkBytes, file.size) / file.size)
  }
  return hasher.hex()
}
