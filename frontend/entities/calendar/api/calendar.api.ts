import { apiClient } from '@/shared/api'
import type { CalendarDates, CalendarMonthParams, CalendarDayItem, CalendarDayParams } from '../model/types'

/** GET /calendar — 월별 문서 조회 (캘린더 셀 렌더링용) */
export async function fetchCalendarMonth(params: CalendarMonthParams): Promise<CalendarDates> {
  const query = new URLSearchParams({
    year: String(params.year),
    month: String(params.month),
  })
  if (params.category) query.set('category', params.category)
  const res = await apiClient<{ dates: CalendarDates }>(`/calendar?${query.toString()}`, {
    requireAuth: true,
  })
  return res.data.dates
}

/** GET /calendar/day — 일별 문서 조회 (날짜 클릭 시 상세 목록) */
export async function fetchCalendarDay(params: CalendarDayParams): Promise<CalendarDayItem[]> {
  const query = new URLSearchParams({ date: params.date })
  if (params.category) query.set('category', params.category)
  const res = await apiClient<{ items: CalendarDayItem[] }>(`/calendar/day?${query.toString()}`, {
    requireAuth: true,
  })
  return res.data.items
}
