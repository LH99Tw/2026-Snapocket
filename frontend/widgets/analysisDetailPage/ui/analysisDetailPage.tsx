'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiFetchBlobUrl, fetchDocument, deleteDocument } from '@/entities/document'
import {
  confirmAnalysis,
  fetchAnalysisResult,
  fetchAnalysisStatus,
  isoToDisplay,
  displayToIso,
} from '@/entities/analysis'
import { MOCK_DOCUMENTS } from '@/entities/document'
import { MOCK_RESULTS } from '@/entities/analysis'
import type { DocumentStatus } from '@/entities/document'
import { ApiError } from '@/shared/api'

// ── 로컬 타입 ────────────────────────────────────────────────────────────────

type PageStatus = 'loading' | 'polling' | 'ready' | 'not-started' | 'failed' | 'saving' | 'discarding'

interface TagItem {
  id: number
  label: string // '#CS-204' 형태
  color: string
}

interface FormState {
  title: string
  category: string
  captureDate: string // MM/DD/YYYY (표시용)
  summary: string
  tags: TagItem[]
}

const CATEGORY_OPTIONS = [
  'Class Materials',
  'Research Papers',
  'Personal Notes',
  'Assignments',
  'Receipts',
  'Notices',
]

const POLL_INTERVAL_MS = 3_000

// ── 유틸 ─────────────────────────────────────────────────────────────────────

function tagColor(label: string): string {
  const colors = ['#81ecff', '#ac89ff', '#fab0ff']
  const hash = label.split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return colors[hash % colors.length]
}

function rawTagName(label: string): string {
  return label.startsWith('#') ? label.slice(1) : label
}

function isMockId(id: string): boolean {
  return id.startsWith('mock-')
}

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────

export function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [pageStatus, setPageStatus] = useState<PageStatus>('loading')
  const [documentStatus, setDocumentStatus] = useState<DocumentStatus | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const [form, setForm] = useState<FormState>({
    title: '',
    category: '',
    captureDate: '',
    summary: '',
    tags: [],
  })

  const [categoryOpen, setCategoryOpen] = useState(false)
  const [addingTag, setAddingTag] = useState(false)
  const [newTag, setNewTag] = useState('')

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const imageBlobRef = useRef<string | null>(null)

  // ── 초기 로딩 ─────────────────────────────────────────────────────────────

  const loadResult = useCallback(async () => {
    if (isMockId(id)) {
      const result = MOCK_RESULTS[id]
      if (!result) {
        setErrorMsg('Mock 데이터를 찾을 수 없습니다')
        setPageStatus('failed')
        return
      }
      setForm({
        title: result.title,
        category: result.category,
        captureDate: isoToDisplay(result.capture_date),
        summary: result.summary,
        tags: result.tags.map((t, i) => ({
          id: i,
          label: t.startsWith('#') ? t : `#${t}`,
          color: tagColor(t),
        })),
      })
      setDocumentStatus('analyzed')
      setPageStatus('ready')
      return
    }

    try {
      const result = await fetchAnalysisResult(id)
      setForm({
        title: result.title,
        category: result.category,
        captureDate: isoToDisplay(result.capture_date),
        summary: result.summary,
        tags: result.tags.map((t, i) => ({
          id: i,
          label: t.startsWith('#') ? t : `#${t}`,
          color: tagColor(t),
        })),
      })
      setDocumentStatus('analyzed')
      setPageStatus('ready')
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : '분석 결과 로드 실패')
      setPageStatus('failed')
    }
  }, [id])

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return

    setPageStatus('polling')

    pollTimerRef.current = setInterval(async () => {
      try {
        const statusData = await fetchAnalysisStatus(id)
        setDocumentStatus(statusData.status)

        if (statusData.status === 'analyzed') {
          clearInterval(pollTimerRef.current!)
          pollTimerRef.current = null
          await loadResult()
        } else if (statusData.status === 'failed') {
          clearInterval(pollTimerRef.current!)
          pollTimerRef.current = null
          setPageStatus('failed')
        }
      } catch {
        // 네트워크 오류 — 다음 폴링 주기에 재시도
      }
    }, POLL_INTERVAL_MS)
  }, [id, loadResult])

  useEffect(() => {
    if (!id) return

    // mock 데이터 처리
    if (isMockId(id)) {
      const doc = MOCK_DOCUMENTS[id]
      if (!doc) {
        setErrorMsg('Mock 데이터를 찾을 수 없습니다')
        setPageStatus('failed')
        return
      }
      setForm({
        title: doc.title,
        category: doc.category,
        captureDate: isoToDisplay(doc.capture_date),
        summary: doc.summary,
        tags: doc.tags.map((t, i) => ({
          id: i,
          label: t.startsWith('#') ? t : `#${t}`,
          color: tagColor(t),
        })),
      })
      setDocumentStatus('analyzed')
      setPageStatus('ready')
      return
    }

    let alive = true
    let blobUrl: string | null = null

    async function init() {
      setPageStatus('loading')
      setErrorMsg(null)

      // 문서 정보 + 이미지를 병렬로 요청
      const [docResult, blobResult] = await Promise.allSettled([
        fetchDocument(id),
        apiFetchBlobUrl(`/documents/${id}/file`),
      ])

      if (!alive) return

      if (docResult.status === 'rejected') {
        const err = docResult.reason
        setErrorMsg(err instanceof ApiError ? err.message : '문서 로드 실패')
        setPageStatus('failed')
        return
      }

      const doc = docResult.value

      if (blobResult.status === 'fulfilled') {
        blobUrl = blobResult.value
        imageBlobRef.current = blobUrl
        setImageUrl(blobUrl)
      }

      // 이미 document에 데이터가 있으면 폼 기본값으로 세팅
      setForm({
        title: doc.title,
        category: doc.category,
        captureDate: isoToDisplay(doc.capture_date),
        summary: doc.summary,
        tags: doc.tags.map((t, i) => ({
          id: i,
          label: t.startsWith('#') ? t : `#${t}`,
          color: tagColor(t),
        })),
      })

      setDocumentStatus(doc.status)

      switch (doc.status) {
        case 'analyzed':
          await loadResult()
          break
        case 'processing':
          startPolling()
          break
        case 'uploaded':
          setPageStatus('not-started')
          break
        case 'failed':
          setPageStatus('failed')
          break
      }
    }

    init()

    return () => {
      alive = false
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [id, loadResult, startPolling])

  // ── 액션 핸들러 ────────────────────────────────────────────────────────────

  async function handleConfirm() {
    if (isMockId(id)) {
      router.push('/')
      return
    }
    setPageStatus('saving')
    try {
      await confirmAnalysis(id, {
        title: form.title,
        category: form.category,
        capture_date: displayToIso(form.captureDate),
        summary: form.summary,
        tags: form.tags.map((t) => rawTagName(t.label)),
      })
      router.push('/')
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : '저장 실패')
      setPageStatus('ready')
    }
  }

  async function handleRecalibrate() {
    if (isMockId(id)) return
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
    try {
      await retryAnalysisCall()
      startPolling()
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : '재분석 요청 실패')
    }
  }

  async function retryAnalysisCall() {
    const { retryAnalysis } = await import('@/entities/analysis')
    await retryAnalysis(id)
  }

  async function handleDiscard() {
    if (isMockId(id)) {
      router.push('/')
      return
    }
    if (!confirm('추출 데이터를 삭제하고 목록으로 돌아갑니다. 계속할까요?')) return
    setPageStatus('discarding')
    try {
      await deleteDocument(id)
      router.push('/')
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : '삭제 실패')
      setPageStatus('ready')
    }
  }

  function handleAddTag() {
    const trimmed = newTag.trim()
    if (!trimmed) return
    const label = trimmed.startsWith('#') ? trimmed : `#${trimmed}`
    setForm((f) => ({
      ...f,
      tags: [...f.tags, { id: Date.now(), label, color: tagColor(label) }],
    }))
    setNewTag('')
    setAddingTag(false)
  }

  function handleRemoveTag(tagId: number) {
    setForm((f) => ({ ...f, tags: f.tags.filter((t) => t.id !== tagId) }))
  }

  // ── 상태별 overlay 렌더링 ──────────────────────────────────────────────────

  const isProcessing = pageStatus === 'loading' || pageStatus === 'polling'
  const isSaving = pageStatus === 'saving'
  const isDiscarding = pageStatus === 'discarding'
  const isInteractive = pageStatus === 'ready' && documentStatus === 'analyzed'

  // ── 렌더링 ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-snap-bg font-inter">
      {/* ── Top Header ─────────────────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center justify-between px-8 h-[77px] bg-[#171a1d]/70 border-b border-snap-border/10 backdrop-blur-md">
        {/* 좌측 */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.back()}
            className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-white/5"
            aria-label="뒤로 가기"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M10 3L5 8L10 13"
                stroke="#aaabaf"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          <div className="flex flex-col">
            <span className="font-manrope font-extrabold text-[20px] leading-[28px] tracking-[-0.5px] text-snap-white">
              Analysis Detail
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`inline-block rounded-full w-2 h-2 transition-colors duration-300 ${
                  isProcessing ? 'bg-amber-500' : pageStatus === 'failed' ? 'bg-red-600' : 'bg-snap-cyan'
                }`}
              />
              <span className="text-[12px] font-normal tracking-[1.2px] text-snap-muted leading-[16px]">
                {isProcessing
                  ? 'Analyzing...'
                  : pageStatus === 'failed'
                    ? 'Analysis Failed'
                    : isSaving
                      ? 'Saving...'
                      : 'Editing Extracted Data'}
              </span>
            </div>
          </div>
        </div>

        {/* 우측: Confirm and Save */}
        <button
          onClick={handleConfirm}
          disabled={!isInteractive || isSaving}
          className="flex items-center justify-center rounded-full transition-opacity disabled:cursor-not-allowed disabled:opacity-40 hover:opacity-90 w-[184px] h-[44px] bg-gradient-to-br from-snap-cyan to-snap-cyan-3"
        >
          <span className="text-[14px] font-bold text-snap-btn-text">
            {isSaving ? 'Saving…' : 'Confirm and Save'}
          </span>
        </button>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────────── */}
      <main className="flex flex-1 gap-12 overflow-hidden px-8 py-8">

        {/* ── Left Panel (38%) ─────────────────────────────────────────────── */}
        <div className="flex w-[38.4%] shrink-0 flex-col gap-4">
          {/* Image container */}
          <div
            className="relative flex-1 overflow-hidden rounded-xl bg-black border border-snap-border/15 min-h-0"
          >
            {imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={imageUrl}
                alt="Original document"
                className="absolute inset-0 h-full w-full object-contain"
              />
            ) : (
              <div
                className="absolute inset-0"
                style={{
                  background:
                    'radial-gradient(ellipse at 30% 40%, rgba(0,180,210,0.07) 0%, transparent 60%), radial-gradient(ellipse at 70% 70%, rgba(172,137,255,0.05) 0%, transparent 60%)',
                }}
              />
            )}

            {/* 스캔 라인 */}
            {isProcessing && (
              <div
                className="pointer-events-none absolute left-0 right-0 top-0 h-[2px] bg-snap-cyan/40"
                style={{
                  animation: 'scan-line 2.4s linear infinite',
                }}
              />
            )}

            {/* 로딩 / 처리 중 오버레이 */}
            {isProcessing && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <div
                  className="h-8 w-8 rounded-full border-2 border-snap-cyan/20 border-t-snap-cyan"
                  style={{
                    animation: 'spin 0.9s linear infinite',
                  }}
                />
                <span className="text-[11px] font-semibold tracking-[2px] text-snap-cyan/50">
                  {pageStatus === 'polling' ? 'ANALYZING…' : 'LOADING…'}
                </span>
              </div>
            )}

            {/* 실패 오버레이 */}
            {pageStatus === 'failed' && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <span className="text-[11px] font-semibold tracking-[2px] text-red-600">
                  ANALYSIS FAILED
                </span>
                {errorMsg && (
                  <span className="text-[10px] text-red-600/60 max-w-[80%] text-center">
                    {errorMsg}
                  </span>
                )}
              </div>
            )}

            <style>{`
              @keyframes scan-line {
                0%   { top: 0%; opacity: 1; }
                80%  { opacity: 1; }
                100% { top: 100%; opacity: 0; }
              }
              @keyframes spin {
                to { transform: rotate(360deg); }
              }
            `}</style>
          </div>

          {/* 하단 버튼 */}
          <div className="flex shrink-0 gap-2">
            <button
              onClick={handleRecalibrate}
              disabled={isProcessing || isSaving || isDiscarding}
              className="flex flex-1 items-center justify-center rounded-lg transition-colors hover:bg-white/5 disabled:opacity-40 h-12 bg-[#171a1d]"
            >
              <span className="text-[12px] font-normal tracking-[1.2px] text-snap-muted">
                Recalibrate AI Lens
              </span>
            </button>
            <button
              disabled
              className="flex shrink-0 items-center justify-center rounded-lg disabled:opacity-40 w-12 h-12 bg-[#171a1d]"
              aria-label="설정"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="2.5" stroke="#aaabaf" strokeWidth="1.4" />
                <path
                  d="M9 1.5v2M9 14.5v2M1.5 9h2M14.5 9h2M3.7 3.7l1.4 1.4M12.9 12.9l1.4 1.4M3.7 14.3l1.4-1.4M12.9 5.1l1.4-1.4"
                  stroke="#aaabaf"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Right Panel (60%) ────────────────────────────────────────────── */}
        <div className="flex flex-1 min-w-0 flex-col gap-8 overflow-y-auto">

          {/* Document Title */}
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-normal tracking-[2px] text-snap-muted leading-[15px]">
              DOCUMENT TITLE
            </label>
            <div className="rounded-lg px-3 py-3.5 border border-gray-500">
              <input
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                disabled={!isInteractive}
                className="w-full bg-transparent outline-none disabled:opacity-60 text-[36px] font-semibold leading-[40px] text-snap-white"
                placeholder={isProcessing ? 'Analyzing…' : '문서 제목'}
              />
            </div>
          </div>

          {/* Category + Date */}
          <div className="flex gap-8">
            {/* Category */}
            <div className="relative flex flex-1 flex-col gap-1.5">
              <label className="text-[10px] font-normal tracking-[2px] text-snap-muted leading-[15px]">
                CATEGORY
              </label>
              <button
                onClick={() => isInteractive && setCategoryOpen((v) => !v)}
                disabled={!isInteractive}
                className="flex items-center justify-between rounded-lg px-4 disabled:opacity-60 h-[44px] bg-snap-input"
              >
                <span className="text-[14px] font-medium text-snap-white">
                  {form.category || '—'}
                </span>
                <svg
                  width="21"
                  height="21"
                  viewBox="0 0 21 21"
                  fill="none"
                  style={{
                    transform: categoryOpen ? 'rotate(180deg)' : 'rotate(0)',
                    transition: 'transform 0.15s',
                  }}
                >
                  <path d="M5 8L10.5 13.5L16 8" stroke="#aaabaf" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {categoryOpen && (
                <div
                  className="absolute left-0 right-0 z-20 overflow-hidden rounded-lg bg-[#1d2024] border border-snap-border/30 top-[calc(100%+4px)]"
                >
                  {CATEGORY_OPTIONS.map((opt) => (
                    <button
                      key={opt}
                      onClick={() => { setForm((f) => ({ ...f, category: opt })); setCategoryOpen(false) }}
                      className={`flex w-full items-center px-4 transition-colors hover:bg-white/5 h-10 text-[14px] ${opt === form.category ? 'font-semibold text-snap-cyan' : 'font-normal text-snap-white'}`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Capture Date */}
            <div className="flex flex-1 flex-col gap-1.5">
              <label className="text-[10px] font-normal tracking-[2px] text-snap-muted leading-[15px]">
                CAPTURE DATE
              </label>
              <div
                className="flex items-center justify-between rounded-lg px-4 h-[44px] bg-snap-input"
              >
                <input
                  type="text"
                  value={form.captureDate}
                  onChange={(e) => setForm((f) => ({ ...f, captureDate: e.target.value }))}
                  disabled={!isInteractive}
                  className="bg-transparent outline-none disabled:opacity-60 text-[14px] font-medium text-snap-white"
                  placeholder="MM/DD/YYYY"
                />
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" opacity={0.4}>
                  <rect x="1.5" y="3" width="15" height="13.5" rx="2" stroke="#aaabaf" strokeWidth="1.4" />
                  <path d="M5.5 1.5V4.5M12.5 1.5V4.5M1.5 7.5H16.5" stroke="#aaabaf" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              </div>
            </div>
          </div>

          {/* Content Summary */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-normal tracking-[2px] text-snap-muted leading-[15px]">
                CONTENT SUMMARY
              </span>
              <div className="flex items-center gap-1.5">
                <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                  <circle cx="5.5" cy="5.5" r="4.5" stroke="#81ecff" strokeWidth="1" />
                  <path d="M5.5 3.5V5.5M5.5 7.5V7.6" stroke="#81ecff" strokeWidth="1" strokeLinecap="round" />
                </svg>
                <span className="text-[10px] font-bold text-snap-cyan leading-[15px]">
                  AI GENERATED
                </span>
              </div>
            </div>
            <textarea
              value={form.summary}
              onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
              disabled={!isInteractive}
              className="w-full resize-none rounded-xl px-6 py-6 outline-none disabled:opacity-60 h-[300px] bg-snap-input text-[16px] font-normal leading-[26px] text-snap-muted"
              placeholder={isProcessing ? 'Analyzing content…' : ''}
            />
          </div>

          {/* Knowledge Tags */}
          <div className="flex flex-col gap-2">
            <span className="text-[10px] font-normal tracking-[2px] text-snap-muted leading-[15px]">
              TAGS
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {form.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="group flex items-center gap-1 rounded-md px-3 py-1 bg-[#292c31]"
                  style={{ border: `1px solid ${tag.color}33` }}
                >
                  <span className="text-[12px] font-bold leading-[16px]" style={{ color: tag.color }}>
                    {tag.label}
                  </span>
                  {isInteractive && (
                    <button
                      onClick={() => handleRemoveTag(tag.id)}
                      className="ml-0.5 opacity-0 transition-opacity group-hover:opacity-60"
                      aria-label="태그 제거"
                    >
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                        <path d="M2 2L8 8M8 2L2 8" stroke={tag.color} strokeWidth="1.3" strokeLinecap="round" />
                      </svg>
                    </button>
                  )}
                </span>
              ))}

              {isInteractive && (
                addingTag ? (
                  <input
                    autoFocus
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAddTag(); if (e.key === 'Escape') setAddingTag(false) }}
                    onBlur={handleAddTag}
                    className="rounded-md px-3 outline-none h-[26px] bg-[#292c31] border border-snap-cyan/30 text-[12px] font-bold text-snap-cyan w-[100px]"
                    placeholder="#tag"
                  />
                ) : (
                  <button
                    onClick={() => setAddingTag(true)}
                    className="flex items-center justify-center rounded-md px-3 transition-colors hover:bg-white/5 h-[26px] bg-[#1d2024] text-[12px] font-normal text-snap-muted"
                  >
                    + Add Tag
                  </button>
                )
              )}
            </div>
          </div>

          {/* Footer */}
          <div
            className="mt-auto flex items-center pt-6 border-t border-snap-border/10"
          >
            <button
              onClick={handleDiscard}
              disabled={isDiscarding || isSaving}
              className="flex items-center gap-2 transition-opacity hover:opacity-70 disabled:opacity-40"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 4H14M5 4V2.5C5 2 5.5 1.5 6 1.5H10C10.5 1.5 11 2 11 2.5V4M6.5 7V12M9.5 7V12M3.5 4L4.5 13.5C4.5 14 5 14.5 5.5 14.5H10.5C11 14.5 11.5 14 11.5 13.5L12.5 4" stroke="#d7383b" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-[14px] font-semibold text-red-600 leading-[20px]">
                {isDiscarding ? 'Discarding…' : 'Discard Extraction'}
              </span>
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
