// Attachment download via the authorized axios client (token-refresh
// interceptor applies — never use bare links/XHR here).
import { api } from '../api/client'

/** Stream an attachment as a blob and trigger a browser download. */
export async function downloadAttachment(fileId: number, name: string | null): Promise<void> {
  const res = await api.get(`/files/${fileId}/download`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(res.data)
  const link = document.createElement('a')
  link.href = url
  link.download = name ?? 'file'
  link.click()
  URL.revokeObjectURL(url)
}
