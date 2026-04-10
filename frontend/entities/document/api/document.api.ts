import { apiClient, apiFetchBlobUrl } from '@/shared/api'
import type {
  DocumentDetail,
  DocumentListItem,
  DocumentListParams,
  PaginationMeta,
  UpdateDocumentPayload,
  UploadResponse,
} from '../model/types'

export { apiFetchBlobUrl }

export async function fetchDocuments(
  params?: DocumentListParams,
): Promise<{ items: DocumentListItem[]; pagination: PaginationMeta }> {
  const query = new URLSearchParams()
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        query.set(key, String(value))
      }
    })
  }
  const qs = query.toString()
  const res = await apiClient<{ items: DocumentListItem[]; pagination: PaginationMeta }>(
    `/documents${qs ? `?${qs}` : ''}`,
    { requireAuth: true },
  )
  return res.data
}

export async function uploadDocument(
  file: File,
  autoAnalyze = true,
): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('autoAnalyze', String(autoAnalyze))

  const res = await apiClient<UploadResponse>('/documents/upload', {
    method: 'POST',
    body: form,
    requireAuth: true,
  })
  return res.data
}

export async function fetchDocument(id: string): Promise<DocumentDetail> {
  const res = await apiClient<{ document: DocumentDetail }>(`/documents/${id}`, { requireAuth: true })
  return res.data.document
}

export async function updateDocument(
  id: string,
  payload: UpdateDocumentPayload,
): Promise<DocumentDetail> {
  const res = await apiClient<{ document: DocumentDetail }>(`/documents/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    requireAuth: true,
  })
  return res.data.document
}

export async function deleteDocument(id: string): Promise<void> {
  await apiClient<unknown>(`/documents/${id}`, { method: 'DELETE', requireAuth: true })
}

/** GET /documents/{id}/file — 이미지 미리보기 / 오디오 플레이어용 Blob Object URL 반환 */
export async function getDocumentFile(id: string): Promise<string> {
  return apiFetchBlobUrl(`/documents/${id}/file`)
}
