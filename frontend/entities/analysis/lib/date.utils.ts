/** ISO8601 → MM/DD/YYYY (화면 표시용) */
export function isoToDisplay(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${m}/${day}/${d.getUTCFullYear()}`
}

/** MM/DD/YYYY → ISO8601 (API 전송용). 변환 실패 시 원문 반환. */
export function displayToIso(display: string): string {
  const parts = display.split('/')
  if (parts.length !== 3) return display
  const [m, d, y] = parts
  const date = new Date(`${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}T00:00:00.000Z`)
  return isNaN(date.getTime()) ? display : date.toISOString()
}
