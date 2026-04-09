export type DocumentStatus = 'uploaded' | 'processing' | 'analyzed' | 'failed'
export type FileType = 'image' | 'audio'

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
