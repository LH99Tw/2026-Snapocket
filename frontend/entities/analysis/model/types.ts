/** GET /analysis/{id}/status → data */
export interface AnalysisStatus {
  status: import('@/entities/document').DocumentStatus
  started_at: string | null
  finished_at: string | null
}

/** GET /analysis/{id}/result → data */
export interface AnalysisResult {
  title: string
  category: string
  capture_date: string | null
  summary: string
  tags: string[]
  raw_text: string
  key_concepts: string[]
  deadline: string | null
}

/** POST /analysis/{id}/confirm request body */
export interface ConfirmPayload {
  title: string
  category: string
  capture_date: string
  summary: string
  tags: string[]
}
