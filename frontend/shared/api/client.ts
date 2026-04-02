export const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly errorCode?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export function saveAccessToken(token: string): void {
  localStorage.setItem("access_token", token);
}

export function clearAccessToken(): void {
  localStorage.removeItem("access_token");
}

export async function apiClient<T>(
  path: string,
  options: RequestInit & { requireAuth?: boolean } = {}
): Promise<ApiResponse<T>> {
  const { requireAuth = false, headers: rawHeaders, ...fetchOptions } = options;

  const headers = new Headers(rawHeaders as HeadersInit | undefined);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (requireAuth) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...fetchOptions,
    headers,
  });

  const body = await res.json().catch(() => null) as (ApiResponse<T> & { error_code?: string }) | null;

  if (!res.ok) {
    throw new ApiError(
      res.status,
      body?.message ?? res.statusText,
      body?.error_code
    );
  }

  return body as ApiResponse<T>;
}
