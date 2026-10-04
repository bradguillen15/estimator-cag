import { t } from '../i18n/locale'
import type { EstimationRequest, PromptContext, SessionCreatedResponse, SessionEstimationResponse } from './types'

/** Empty = same origin (Vite proxy in dev, FastAPI serving web/dist in prod). */
const API_BASE: string = import.meta.env.VITE_API_URL ?? ''

export const API_LABEL = API_BASE || window.location.origin

export class ApiError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(t('error.connect', { api: API_LABEL }))
  }
  if (!response.ok) throw await toApiError(response)
  return response
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail = response.statusText
  try {
    const body: { detail?: unknown } = await response.json()
    detail = formatDetail(body.detail) ?? detail
  } catch {
    // Non-JSON error body: keep the status text.
  }
  return new ApiError(t('error.http', { status: response.status, detail }), response.status)
}

/** FastAPI returns a string for HTTPException and a list of issues for 422s. */
function formatDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((issue: { loc?: unknown[]; msg?: string }) => `${issue.loc?.at(-1) ?? ''}: ${issue.msg}`).join('; ')
  }
  return undefined
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`)
    return response.ok
  } catch {
    return false
  }
}

export async function getPromptContext(): Promise<PromptContext> {
  const response = await send('/api/v1/context')
  return response.json()
}

export async function createSession(signal?: AbortSignal): Promise<SessionCreatedResponse> {
  const response = await send('/api/v1/sessions', { method: 'POST', signal })
  return response.json()
}

/** Multipart request: no explicit Content-Type, the browser adds the boundary. */
export async function createSessionEstimate(
  sessionId: string,
  request: EstimationRequest,
  files: File[],
  signal?: AbortSignal,
): Promise<SessionEstimationResponse> {
  const form = new FormData()
  form.append('transcript', request.description)
  form.append('project_type', request.project_type)
  form.append('detail_level', request.detail_level)
  form.append('output_format', request.output_format)
  form.append('language', request.language)
  for (const file of files) form.append('attachments', file)

  const response = await send(`/api/v1/sessions/${encodeURIComponent(sessionId)}/estimate`, {
    method: 'POST',
    body: form,
    signal,
  })
  return response.json()
}
