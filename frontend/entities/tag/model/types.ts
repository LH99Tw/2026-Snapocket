/** GET /tags → data.tags[] */
export interface Tag {
  id: string
  name: string
  count: number
}

/** POST/PATCH /documents/{id}/tags → data.tags[] */
export interface DocumentTag {
  id: string
  name: string
}

/** GET /tags query params */
export interface TagListParams {
  keyword?: string
}

/** POST /documents/{id}/tags request body */
export interface AddTagsPayload {
  tags: string[]
}

/** PATCH /documents/{id}/tags request body */
export interface ReplaceTagsPayload {
  tags: string[]
}
