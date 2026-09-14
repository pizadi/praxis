import { Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { Appointment } from '../api/types'

/**
 * Deprecated: appointments now open inside the patient page. Kept as a
 * redirect for old bookmarks/links.
 */
export default function AppointmentPage() {
  const { id } = useParams<{ id: string }>()

  const { data: a } = useQuery({
    queryKey: ['appointment', id],
    queryFn: async () => (await api.get<Appointment>(`/appointments/${id}`)).data,
  })

  if (!a) return null
  return <Navigate to={`/patients/${a.patient_id}?appt=${a.id}`} replace />
}
