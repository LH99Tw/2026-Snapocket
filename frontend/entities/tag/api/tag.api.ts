import { apiClient } from '@/shared/api'
import type { Tag, DocumentTag, TagListParams, AddTagsPayload, ReplaceTagsPayload } from '../model/types'

/** GET /tags — 전체 태그 목록 조회 (태그 필터 칩 UI용) */
export async function fetchTags(params?: TagListParams): Promise<Tag[]> {
  const query = new URLSearchParams()
  if (params?.keyword) query.set('keyword', params.keyword)
  const qs = query.toString()
  const res = await apiClient<{ tags: Tag[] }>(`/tags${qs ? `?${qs}` : ''}`, { requireAuth: true })
  return res.data.tags
}

/** POST /documents/{id}/tags — 문서 태그 추가 (일괄) */
export async function addDocumentTags(
  documentId: string,
  payload: AddTagsPayload,
): Promise<DocumentTag[]> {
  const res = await apiClient<{ tags: DocumentTag[] }>(`/documents/${documentId}/tags`, {
    method: 'POST',
    body: JSON.stringify(payload),
    requireAuth: true,
  })
  return res.data.tags
}

/** PATCH /documents/{id}/tags — 문서 태그 전체 교체 */
export async function replaceDocumentTags(
  documentId: string,
  payload: ReplaceTagsPayload,
): Promise<DocumentTag[]> {
  const res = await apiClient<{ tags: DocumentTag[] }>(`/documents/${documentId}/tags`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
    requireAuth: true,
  })
  return res.data.tags
}

/** DELETE /documents/{id}/tags/{tag_id} — 문서 특정 태그 삭제 */
export async function deleteDocumentTag(documentId: string, tagId: string): Promise<void> {
  await apiClient<unknown>(`/documents/${documentId}/tags/${tagId}`, {
    method: 'DELETE',
    requireAuth: true,
  })
}
