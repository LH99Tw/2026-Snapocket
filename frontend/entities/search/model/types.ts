/** GET /search → data.items[] */
export interface SearchItem {
  id: string
  title: string
  category: string
  summary: string
  tags: string[]
  highlight: string
}

/** GET /search query params */
export interface SearchParams {
  keyword: string
  category?: string
  page?: number
  size?: number
}
