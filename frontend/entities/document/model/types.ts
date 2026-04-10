export type DocumentStatus = 'uploaded' | 'processing' | 'analyzed' | 'failed'
export type FileType = 'image' | 'audio'
export type DocumentSortOption = 'created_at_desc' | 'created_at_asc'

/** GET /documents/{id} → data.document */
export interface DocumentDetail {
  id: string
  title: string
  category: string
  summary: string
  tags: string[]
  file_url: string
  file_type: FileType
  status: DocumentStatus
  capture_date: string | null
  deadline: string | null
  created_at: string
}

/** GET /documents → data.items[] */
export interface DocumentListItem {
  id: string
  title: string
  category: string
  status: DocumentStatus
  file_type: FileType
  tags: string[]
  capture_date: string | null
  created_at: string
}

/** GET /documents → data.pagination */
export interface PaginationMeta {
  page: number
  size: number
  total: number
  has_next: boolean
}

/** GET /documents query params */
export interface DocumentListParams {
  page?: number
  size?: number
  keyword?: string
  category?: string
  status?: DocumentStatus
  start_date?: string
  end_date?: string
  sort?: DocumentSortOption
}

/** POST /documents/upload → data */
export interface UploadResponse {
  document_id: string
  file_url: string
  file_type: FileType
  status: 'uploaded' | 'processing'
}

/** PATCH /documents/{id} request body (모두 optional) */
export interface UpdateDocumentPayload {
  title?: string
  category?: string
  capture_date?: string
  summary?: string
}
