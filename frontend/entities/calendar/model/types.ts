import type { FileType } from '@/entities/document'

/** GET /calendar → data.dates의 각 날짜별 항목 */
export interface CalendarDateItem {
  id: string
  title: string
  category: string
  file_type: FileType
}

/** GET /calendar → data.dates (키: YYYY-MM-DD) */
export type CalendarDates = Record<string, CalendarDateItem[]>

/** GET /calendar query params */
export interface CalendarMonthParams {
  year: number
  month: number
  category?: string
}

/** GET /calendar/day → data.items[] */
export interface CalendarDayItem {
  id: string
  title: string
  category: string
  file_type: FileType
  deadline: string | null
}

/** GET /calendar/day query params */
export interface CalendarDayParams {
  date: string
  category?: string
}
