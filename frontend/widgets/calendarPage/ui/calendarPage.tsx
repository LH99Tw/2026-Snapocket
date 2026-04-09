'use client'

import { useState, useRef, useCallback } from 'react'
import { SidebarNav } from '@/shared/ui'
import { UploadModal } from '@/features/upload'

const WEEKDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

/** 월별 Mock 이벤트 — key: "YYYY-MM-DD" */
const MOCK_EVENTS: Record<string, { label: string; color: string }[]> = {
  '2025-10-03': [{ label: 'document 1', color: '#ac89ff' }],
  '2025-10-12': [{ label: 'Active', color: '#81ecff' }],
  '2025-10-17': [{ label: 'document 2', color: '#fab0ff' }],
  '2025-10-24': [{ label: 'Lab Report', color: '#ac89ff' }],
  '2025-10-07': [{ label: 'Lecture Note', color: '#81ecff' }],
  '2025-10-15': [
    { label: 'Assignment', color: '#81ecff' },
    { label: 'Summary', color: '#fab0ff' },
  ],
}

function daysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate()
}

/** 해당 월 1일의 요일 (월요일 기준 0~6) */
function firstWeekdayOfMonth(year: number, month: number) {
  const day = new Date(year, month, 1).getDay() // 0=Sun
  return (day + 6) % 7 // 월=0 … 일=6
}

function buildGrid(year: number, month: number) {
  const totalDays = daysInMonth(year, month)
  const firstDay = firstWeekdayOfMonth(year, month)
  const prevMonthDays = daysInMonth(year, month - 1)

  const cells: { date: Date; current: boolean }[] = []

  // 이전 달 채우기
  for (let i = firstDay - 1; i >= 0; i--) {
    cells.push({
      date: new Date(year, month - 1, prevMonthDays - i),
      current: false,
    })
  }

  // 이번 달
  for (let d = 1; d <= totalDays; d++) {
    cells.push({ date: new Date(year, month, d), current: true })
  }

  // 다음 달 (마지막 행 채우기)
  const tail = cells.length % 7
  if (tail !== 0) {
    for (let d = 1; d <= 7 - tail; d++) {
      cells.push({ date: new Date(year, month + 1, d), current: false })
    }
  }

  // 최소 5주 보장
  while (cells.length < 35) {
    const last = cells[cells.length - 1]
    const next = new Date(last.date)
    next.setDate(next.getDate() + 1)
    cells.push({ date: next, current: false })
  }

  return cells
}

function toKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function CalendarPage() {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [uploadToast, setUploadToast] = useState<{
    visible: boolean
    fileName: string
  }>({ visible: false, fileName: '' })
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cells = buildGrid(year, month)
  const rows: (typeof cells)[] = []
  for (let i = 0; i < cells.length; i += 7) {
    rows.push(cells.slice(i, i + 7))
  }

  const prevMonth = () => {
    if (month === 0) {
      setMonth(11)
      setYear((y) => y - 1)
    } else {
      setMonth((m) => m - 1)
    }
  }

  const nextMonth = () => {
    if (month === 11) {
      setMonth(0)
      setYear((y) => y + 1)
    } else {
      setMonth((m) => m + 1)
    }
  }

  const isToday = (d: Date) =>
    d.getDate() === today.getDate() &&
    d.getMonth() === today.getMonth() &&
    d.getFullYear() === today.getFullYear()

  const getEvents = (d: Date) => MOCK_EVENTS[toKey(d)] ?? []

  // 검색: 이벤트 라벨 필터
  const matchesSearch = (d: Date) => {
    if (!search.trim()) return true
    return getEvents(d).some((e) =>
      e.label.toLowerCase().includes(search.toLowerCase()),
    )
  }

  const handleUpload = useCallback((file: File) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setUploadToast({ visible: true, fileName: file.name })
    toastTimerRef.current = setTimeout(() => {
      setUploadToast({ visible: false, fileName: '' })
    }, 3500)
  }, [])

  return (
    <div
      className="flex h-screen w-full overflow-hidden"
      style={{ background: '#0c0e11' }}
    >
      <SidebarNav onUpload={() => setModalOpen(true)} />

      <main
        className="flex flex-1 flex-col overflow-hidden"
        style={{ marginLeft: 81 }}
      >
        {/* ── 헤더 ─────────────────────────────────── */}
        <header
          className="flex shrink-0 items-center justify-between px-8"
          style={{
            height: 64,
            background: 'rgba(12,14,17,0.7)',
            borderBottom: '1px solid rgba(255,255,255,0.05)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <div className="flex items-center gap-6">
            <span
              className="font-manrope font-semibold text-sm"
              style={{ color: '#aaabaf', letterSpacing: '1.4px' }}
            >
              SCHEDULE
            </span>

            <div className="flex items-center gap-2">
              <span
                className="font-manrope font-bold text-sm"
                style={{ color: '#81ecff', letterSpacing: '1.4px' }}
              >
                {MONTH_NAMES[month].toUpperCase()} {year}
              </span>

              <button
                onClick={prevMonth}
                className="flex h-5 w-4 items-center justify-center rounded transition-opacity hover:opacity-70"
                aria-label="이전 달"
              >
                <svg width="7" height="12" viewBox="0 0 7 12" fill="none">
                  <path
                    d="M6 1L1 6L6 11"
                    stroke="#aaabaf"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>

              <button
                onClick={nextMonth}
                className="flex h-5 w-4 items-center justify-center rounded transition-opacity hover:opacity-70"
                aria-label="다음 달"
              >
                <svg width="7" height="12" viewBox="0 0 7 12" fill="none">
                  <path
                    d="M1 1L6 6L1 11"
                    stroke="#aaabaf"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>

          {/* 검색 */}
          <div
            className="flex items-center gap-2 rounded-full px-4"
            style={{
              width: 256,
              height: 36,
              background: '#111417',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="6" cy="6" r="5" stroke="#747579" strokeWidth="1.3" />
              <path
                d="M10 10L13 13"
                stroke="#747579"
                strokeWidth="1.3"
                strokeLinecap="round"
              />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 bg-transparent font-manrope text-[10px] font-medium tracking-widest outline-none"
              style={{ color: '#aaabaf', letterSpacing: '1.4px' }}
              placeholder="FIND DOCUMENT..."
              aria-label="문서 검색"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                style={{ color: '#747579' }}
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M1 1L9 9M9 1L1 9"
                    stroke="currentColor"
                    strokeWidth="1.3"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            )}
          </div>
        </header>

        {/* ── 캘린더 ───────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* 요일 헤더 */}
          <div
            className="grid shrink-0 grid-cols-7"
            style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
          >
            {WEEKDAYS.map((day) => (
              <div
                key={day}
                className="flex items-center justify-center"
                style={{
                  height: 48,
                  borderRight: '1px solid rgba(255,255,255,0.03)',
                }}
              >
                <span
                  className="font-inter font-bold text-[10px] tracking-[2px]"
                  style={{ color: '#aaabaf' }}
                >
                  {day}
                </span>
              </div>
            ))}
          </div>

          {/* 날짜 행 */}
          <div
            className="grid flex-1 overflow-hidden"
            style={{ gridTemplateRows: `repeat(${rows.length}, 1fr)` }}
          >
            {rows.map((row, rowIdx) => (
              <div
                key={rowIdx}
                className="grid grid-cols-7"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
              >
                {row.map((cell, colIdx) => {
                  const todayCell = isToday(cell.date)
                  const events = getEvents(cell.date)
                  const highlighted = search ? matchesSearch(cell.date) : true

                  return (
                    <div
                      key={colIdx}
                      className="relative flex flex-col overflow-hidden transition-colors"
                      style={{
                        borderRight: '1px solid rgba(255,255,255,0.03)',
                        background: todayCell
                          ? 'rgba(129,236,255,0.03)'
                          : 'transparent',
                        opacity: search && !highlighted ? 0.25 : 1,
                      }}
                    >
                      {/* 날짜 숫자 */}
                      <span
                        className="font-inter font-semibold text-sm"
                        style={{
                          padding: '16px 0 0 16px',
                          display: 'block',
                          color: todayCell
                            ? '#81ecff'
                            : cell.current
                              ? '#f9f9fd'
                              : 'rgba(170,171,175,0.3)',
                        }}
                      >
                        {String(cell.date.getDate()).padStart(2, '0')}
                      </span>

                      {/* 이벤트 */}
                      {events.length > 0 && (
                        <div className="flex flex-col gap-1.5 px-4 pt-2">
                          {events.map((event, i) => (
                            <div key={i} className="flex flex-col gap-1">
                              <div
                                className="rounded-full"
                                style={{
                                  height: 4,
                                  width: 61,
                                  background: event.color,
                                  opacity: todayCell ? 1 : 0.6,
                                }}
                              />
                              <span
                                className="font-inter font-semibold truncate"
                                style={{
                                  fontSize: 8,
                                  letterSpacing: '1.6px',
                                  textTransform: 'uppercase',
                                  color: event.color,
                                  opacity: todayCell ? 1 : 0.6,
                                }}
                              >
                                {event.label}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </main>

      <UploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onUpload={handleUpload}
      />
    </div>
  )
}
