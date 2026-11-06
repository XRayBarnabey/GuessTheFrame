export type ApiErrorPayload = {
  code: string
  message: string
  details?: unknown
}

export class ApiError extends Error {
  code: string
  status: number
  details?: unknown

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message)
    this.name = 'ApiError'
    this.code = payload.code
    this.status = status
    this.details = payload.details
  }
}

let csrfToken: string | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options
  const headers = new Headers({ Accept: 'application/json' })

  if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (method !== 'GET' && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken)
  }

  const response = await fetch(path, {
    method,
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    let payload: ApiErrorPayload = {
      code: 'HTTP_ERROR',
      message: `Erreur HTTP ${response.status}`,
    }
    try {
      const parsed = (await response.json()) as { error?: ApiErrorPayload }
      if (parsed.error) payload = parsed.error
    } catch {
      // Keep the generic error if the body is not JSON.
    }
    throw new ApiError(response.status, payload)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: async <T>(path: string, formData: FormData): Promise<T> => {
    const headers = new Headers({ Accept: 'application/json' })
    if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
    const response = await fetch(path, {
      method: 'POST',
      headers,
      credentials: 'include',
      body: formData,
    })
    if (!response.ok) {
      let payload: ApiErrorPayload = {
        code: 'HTTP_ERROR',
        message: `Erreur HTTP ${response.status}`,
      }
      try {
        const parsed = (await response.json()) as { error?: ApiErrorPayload }
        if (parsed.error) payload = parsed.error
      } catch {
        // Keep the generic error if the body is not JSON.
      }
      throw new ApiError(response.status, payload)
    }
    return (await response.json()) as T
  },
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Une erreur inattendue est survenue.'
}
