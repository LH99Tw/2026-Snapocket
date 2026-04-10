import { apiClient } from '@/shared/api'
import type { SearchItem, SearchParams } from '../model/types'

/** GET /search — 제목/요약/태그 통합 검색 */
export async function searchDocuments(params: SearchParams): Promise<SearchItem[]> {
  const query = new URLSearchParams({ keyword: params.keyword })
  if (params.category) query.set('category', params.category)
  if (params.page !== undefined) query.set('page', String(params.page))
  if (params.size !== undefined) query.set('size', String(params.size))
  const res = await apiClient<{ items: SearchItem[] }>(`/search?${query.toString()}`, {
    requireAuth: true,
  })
  return res.data.items
}
