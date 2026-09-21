import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert } from 'antd'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { useUser } from './AppLayout'

/**
 * Admin-only banner (mounted above the routed page): warns when the last
 * SUCCESSFUL backup is older than BACKUP_STALE_DAYS — or when no backup has
 * ever completed. Server-side `backup_stale` is null when the warning is
 * disabled (stale days = 0).
 */
export default function BackupStaleAlert() {
  const { hasPerm } = useUser()
  const [dismissed, setDismissed] = useState(false)

  const enabled = hasPerm('backup.manage')
  const { data } = useQuery({
    queryKey: ['backup-status'],
    queryFn: async () => (await api.get<BackupStatus>('/admin/backup')).data,
    enabled,
    refetchInterval: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  })

  if (!enabled || dismissed || data?.backup_stale !== true) return null

  const days = data.backup_stale_days
  const description =
    data.last_backup_at == null ? (
      <span>تاکنون هیچ پشتیبانی گرفته نشده است — همان حالا یکی بسازید.</span>
    ) : (
      <span>
        بیش از {days} روز از آخرین پشتیبان‌گیری موفق گذشته است — یک پشتیبان
        تازه بسازید و آن را بیرون از این سامانه ذخیره کنید.
      </span>
    )
  return (
    <Alert
      type="warning"
      showIcon
      closable
      onClose={() => setDismissed(true)}
      style={{ marginBottom: 16 }}
      message="هشدار پشتیبان‌گیری"
      description={
        <>
          {description} <Link to="/backup">رفتن به پشتیبان‌گیری</Link>
        </>
      }
    />
  )
}

interface BackupStatus {
  status: 'idle' | 'running' | 'ready' | 'error'
  sha256: string | null
  encrypted: boolean
  last_backup_at: string | null
  backup_stale: boolean | null
  backup_stale_days: number
}
