import { apiClient } from '@/shared/api'
import type { AnalysisStatus, AnalysisResult, ConfirmPayload, StartAnalysisResponse } from '../model/types'

export async function startAnalysis(documentId: string): Promise<StartAnalysisResponse> {
  const res = await apiClient<StartAnalysisResponse>(`/analysis/${documentId}/start`, {
    method: 'POST',
    requireAuth: true,
  })
  return res.data
}

export async function fetchAnalysisStatus(documentId: string): Promise<AnalysisStatus> {
  const res = await apiClient<AnalysisStatus>(`/analysis/${documentId}/status`, { requireAuth: true })
  return res.data
}

export async function fetchAnalysisResult(documentId: string): Promise<AnalysisResult> {
  const res = await apiClient<AnalysisResult>(`/analysis/${documentId}/result`, { requireAuth: true })
  return res.data
}

export async function confirmAnalysis(documentId: string, payload: ConfirmPayload): Promise<void> {
  await apiClient<unknown>(`/analysis/${documentId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
    requireAuth: true,
  })
}

export async function retryAnalysis(documentId: string): Promise<void> {
  await apiClient<unknown>(`/analysis/${documentId}/retry`, { method: 'POST', requireAuth: true })
}
