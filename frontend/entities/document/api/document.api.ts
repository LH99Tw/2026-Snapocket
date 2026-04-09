import { apiClient, apiFetchBlobUrl } from '@/shared/api'
import type { DocumentDetail } from '../model/types'

export { apiFetchBlobUrl }

export async function fetchDocument(id: string): Promise<DocumentDetail> {
  const res = await apiClient<{ document: DocumentDetail }>(`/documents/${id}`, { requireAuth: true })
  return res.data.document
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient<unknown>(`/documents/${id}`, { method: 'DELETE', requireAuth: true })
}
